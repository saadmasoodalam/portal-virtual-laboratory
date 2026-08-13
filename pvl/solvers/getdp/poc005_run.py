from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path

import numpy as np

from pvl.core.models import MeshConfig, POC003Config
from pvl.core.poc005_models import POC005Config
from pvl.geometry.poc005 import write_axisymmetric_gmsh_geo
from pvl.solvers.getdp.poc001_run import parse_msh2_counts
from pvl.solvers.getdp.poc005 import write_magnetoquasistatic_pro
from pvl.solvers.getdp.runner import (
    ExecutableSet,
    discover_executables,
    generate_mesh,
    run_getdp,
    solver_versions,
)
from pvl.validation.poc003 import dual_coil_phasor_reference
from pvl.validation.poc004 import complex_peak_normalized_error


@dataclass(frozen=True)
class InsertFEMResult:
    axis_z_m: np.ndarray
    b_axis_t: np.ndarray
    insert_r_m: np.ndarray
    j_insert_a_m2: np.ndarray
    joule_loss_w: float
    node_count: int
    element_count: int
    mesh_file: Path


@dataclass(frozen=True)
class InsertConvergencePoint:
    characteristic_length_m: float
    b_axis_t: tuple[complex, ...]
    j_insert_a_m2: tuple[complex, ...]
    joule_loss_w: float
    node_count: int
    element_count: int


@dataclass(frozen=True)
class POC005GateResult:
    passed: bool
    criteria: dict[str, bool]
    observed: dict[str, float | int]
    tolerances: dict[str, float | int]

    def as_dict(self) -> dict[str, object]:
        return {
            "passed": bool(self.passed),
            "criteria": {name: bool(value) for name, value in self.criteria.items()},
            "observed": {
                name: int(value) if isinstance(value, int) else float(value)
                for name, value in self.observed.items()
            },
            "tolerances": {
                name: int(value) if isinstance(value, int) else float(value)
                for name, value in self.tolerances.items()
            },
        }


def parse_getdp_real_scalar_line(
    path: Path,
    *,
    coordinate_column: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Parse one coordinate and an explicitly real scalar from complex GetDP Table output.

    GetDP's line table begins with element metadata followed by x/y/z coordinates. In a complex
    analysis an explicitly real PostProcessing scalar is still serialized as a final
    ``value_real value_imag`` pair. POC-005 therefore reads the penultimate value and lets the
    caller select x (column 2) or y (column 3) as the varying physical coordinate.
    """
    coordinates: list[float] = []
    values_out: list[float] = []
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            values = [float(token) for token in line.replace(",", " ").split()]
        except ValueError:
            continue
        if len(values) < 6 or coordinate_column >= len(values):
            continue
        coordinates.append(values[coordinate_column])
        values_out.append(values[-2])
    if not coordinates:
        raise ValueError(f"No scalar line samples found in GetDP table: {path}")
    coordinate = np.asarray(coordinates, dtype=float)
    field = np.asarray(values_out, dtype=float)
    order = np.argsort(coordinate)
    return coordinate[order], field[order]


def _load_complex_line(
    output_dir: Path,
    real_name: str,
    imag_name: str,
    *,
    coordinate_column: int,
) -> tuple[np.ndarray, np.ndarray]:
    coordinate_re, re = parse_getdp_real_scalar_line(
        output_dir / real_name,
        coordinate_column=coordinate_column,
    )
    coordinate_im, im = parse_getdp_real_scalar_line(
        output_dir / imag_name,
        coordinate_column=coordinate_column,
    )
    if not np.allclose(coordinate_re, coordinate_im, rtol=0.0, atol=1e-14):
        raise ValueError(f"real/imaginary sample coordinates differ: {real_name}, {imag_name}")
    return coordinate_re, re + 1j * im


def _interpolate_complex(x_raw: np.ndarray, values: np.ndarray, target: np.ndarray) -> np.ndarray:
    return np.interp(target, x_raw, np.real(values)) + 1j * np.interp(
        target, x_raw, np.imag(values)
    )


def parse_getdp_global_real(path: Path) -> float:
    """Parse one real global quantity emitted by GetDP from a complex system."""
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            values = [float(token) for token in line.replace(",", " ").split()]
        except ValueError:
            continue
        if not values:
            continue
        if len(values) >= 2:
            return float(values[-2])
        return float(values[-1])
    raise ValueError(f"No global scalar value found in GetDP table: {path}")


def _poc003_reference_config(config: POC005Config) -> POC003Config:
    return POC003Config(
        coil_a=config.coil_a,
        coil_b=config.coil_b,
        drive_a=config.drive_a,
        drive_b=config.drive_b,
        source_section=config.source_section,
        probe_z_m=config.axis_probe_z_m,
    )


def run_conductive_insert_case(
    config: POC005Config,
    output_dir: Path,
    *,
    executables: ExecutableSet | None = None,
) -> InsertFEMResult:
    """Mesh, solve and post-process one POC-005 harmonic state."""
    exe = executables or discover_executables()
    output_dir.mkdir(parents=True, exist_ok=True)

    geo = write_axisymmetric_gmsh_geo(config, output_dir / "poc005_axi.geo")
    pro = write_magnetoquasistatic_pro(config, output_dir / "poc005_axi.pro")
    mesh = generate_mesh(
        geo,
        dimension=2,
        output_path=output_dir / "poc005_axi.msh",
        executables=exe,
    )
    nodes, elements = parse_msh2_counts(mesh)
    run = run_getdp(
        pro,
        mesh,
        resolution="MQ",
        post_operation="Diagnostics",
        executables=exe,
    )
    (output_dir / "solver_stdout.log").write_text(
        run.solve_stdout + "\n--- POST ---\n" + run.post_stdout,
        encoding="utf-8",
    )
    (output_dir / "solver_stderr.log").write_text(
        run.solve_stderr + "\n--- POST ---\n" + run.post_stderr,
        encoding="utf-8",
    )

    raw_z, raw_b = _load_complex_line(
        output_dir,
        "by_axis_re.txt",
        "by_axis_im.txt",
        coordinate_column=3,
    )
    target_z = np.asarray(config.axis_probe_z_m, dtype=float)
    b_axis = _interpolate_complex(raw_z, raw_b, target_z)

    raw_r, raw_j = _load_complex_line(
        output_dir,
        "j_insert_re.txt",
        "j_insert_im.txt",
        coordinate_column=2,
    )
    joule_loss = parse_getdp_global_real(output_dir / "joule_losses.txt")
    if joule_loss < -1e-12:
        raise ValueError(f"computed Joule loss is negative: {joule_loss}")

    versions = solver_versions(exe)
    payload = {
        "experiment": config.model_dump(mode="json"),
        "configuration_hash": config.configuration_hash(),
        "solver_versions": {"gmsh": versions.gmsh, "getdp": versions.getdp},
        "mesh": {"nodes": nodes, "elements": elements},
        "insert_skin_depth_m": config.insert_skin_depth_m,
        "joule_loss_w": joule_loss,
        "axis_probe_results": [
            {
                "z_m": float(z),
                "b_re_t": float(value.real),
                "b_im_t": float(value.imag),
                "b_abs_t": float(abs(value)),
            }
            for z, value in zip(target_z, b_axis)
        ],
        "insert_current_line": [
            {
                "r_m": float(r),
                "j_re_a_m2": float(value.real),
                "j_im_a_m2": float(value.imag),
                "j_abs_a_m2": float(abs(value)),
            }
            for r, value in zip(raw_r, raw_j)
        ],
    }
    (output_dir / "metrics.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    return InsertFEMResult(
        axis_z_m=target_z,
        b_axis_t=b_axis,
        insert_r_m=raw_r,
        j_insert_a_m2=raw_j,
        joule_loss_w=max(0.0, joule_loss),
        node_count=nodes,
        element_count=elements,
        mesh_file=mesh,
    )


def vacuum_reference_error(config: POC005Config, result: InsertFEMResult) -> dict[str, float]:
    if config.insert.conductivity_s_m != 0.0 or not math.isclose(
        config.insert.relative_permeability, 1.0, rel_tol=0.0, abs_tol=1e-15
    ):
        raise ValueError("vacuum reference requires sigma=0 and relative permeability=1")
    reference = dual_coil_phasor_reference(_poc003_reference_config(config))
    return complex_peak_normalized_error(reference.b_phasor_t, result.b_axis_t)


def run_insert_mesh_convergence(
    base_config: POC005Config,
    output_dir: Path,
    *,
    characteristic_lengths_m: tuple[float, ...] = (0.01, 0.007, 0.005),
    executables: ExecutableSet | None = None,
) -> list[InsertConvergencePoint]:
    if len(characteristic_lengths_m) < 2:
        raise ValueError("POC-005 convergence requires at least two mesh sizes")
    if any(a <= b for a, b in zip(characteristic_lengths_m, characteristic_lengths_m[1:])):
        raise ValueError("mesh sizes must be strictly descending from coarse to fine")

    exe = executables or discover_executables()
    points: list[InsertConvergencePoint] = []
    payload: list[dict[str, object]] = []
    previous_b: np.ndarray | None = None
    previous_j: np.ndarray | None = None
    previous_loss: float | None = None

    for index, h in enumerate(characteristic_lengths_m, start=1):
        config = base_config.model_copy(
            update={"mesh": MeshConfig(characteristic_length_m=h, order=base_config.mesh.order)}
        )
        result = run_conductive_insert_case(
            config,
            output_dir / f"mesh_{index:02d}",
            executables=exe,
        )
        point = InsertConvergencePoint(
            characteristic_length_m=h,
            b_axis_t=tuple(complex(v) for v in result.b_axis_t),
            j_insert_a_m2=tuple(complex(v) for v in result.j_insert_a_m2),
            joule_loss_w=result.joule_loss_w,
            node_count=result.node_count,
            element_count=result.element_count,
        )
        points.append(point)

        b = np.asarray(point.b_axis_t, dtype=complex)
        j = np.asarray(point.j_insert_a_m2, dtype=complex)
        b_change = None
        j_change = None
        loss_change = None
        if previous_b is not None:
            b_scale = max(float(np.max(np.abs(b))), np.finfo(float).tiny)
            b_change = float(np.max(np.abs(b - previous_b)) / b_scale)
        if previous_j is not None:
            j_scale = max(float(np.max(np.abs(j))), np.finfo(float).tiny)
            j_change = float(np.max(np.abs(j - previous_j)) / j_scale)
        if previous_loss is not None:
            loss_scale = max(abs(point.joule_loss_w), np.finfo(float).tiny)
            loss_change = float(abs(point.joule_loss_w - previous_loss) / loss_scale)
        payload.append(
            {
                "characteristic_length_m": h,
                "nodes": point.node_count,
                "elements": point.element_count,
                "joule_loss_w": point.joule_loss_w,
                "successive_b_peak_normalized_change": b_change,
                "successive_j_peak_normalized_change": j_change,
                "successive_joule_relative_change": loss_change,
            }
        )
        previous_b = b
        previous_j = j
        previous_loss = point.joule_loss_w

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "convergence.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return points


def superposition_errors(
    combined: InsertFEMResult,
    a_only: InsertFEMResult,
    b_only: InsertFEMResult,
) -> dict[str, float]:
    expected_b = a_only.b_axis_t + b_only.b_axis_t
    expected_j = a_only.j_insert_a_m2 + b_only.j_insert_a_m2
    b_scale = max(float(np.max(np.abs(expected_b))), np.finfo(float).tiny)
    j_scale = max(float(np.max(np.abs(expected_j))), np.finfo(float).tiny)
    return {
        "b_max_peak_normalized_superposition_error": float(
            np.max(np.abs(combined.b_axis_t - expected_b)) / b_scale
        ),
        "j_max_peak_normalized_superposition_error": float(
            np.max(np.abs(combined.j_insert_a_m2 - expected_j)) / j_scale
        ),
    }


def _final_changes(points: list[InsertConvergencePoint]) -> tuple[float, float, float]:
    if len(points) < 2:
        return float("inf"), float("inf"), float("inf")
    prev = points[-2]
    cur = points[-1]
    prev_b = np.asarray(prev.b_axis_t, dtype=complex)
    cur_b = np.asarray(cur.b_axis_t, dtype=complex)
    prev_j = np.asarray(prev.j_insert_a_m2, dtype=complex)
    cur_j = np.asarray(cur.j_insert_a_m2, dtype=complex)
    b_scale = max(float(np.max(np.abs(cur_b))), np.finfo(float).tiny)
    j_scale = max(float(np.max(np.abs(cur_j))), np.finfo(float).tiny)
    loss_scale = max(abs(cur.joule_loss_w), np.finfo(float).tiny)
    return (
        float(np.max(np.abs(cur_b - prev_b)) / b_scale),
        float(np.max(np.abs(cur_j - prev_j)) / j_scale),
        float(abs(cur.joule_loss_w - prev.joule_loss_w) / loss_scale),
    )


def _mesh_checks(points: list[InsertConvergencePoint]) -> tuple[bool, bool, bool]:
    sizes = all(
        a.characteristic_length_m > b.characteristic_length_m for a, b in zip(points, points[1:])
    )
    nodes = all(a.node_count < b.node_count for a, b in zip(points, points[1:]))
    elements = all(a.element_count < b.element_count for a, b in zip(points, points[1:]))
    return sizes, nodes, elements


def evaluate_poc005_gate(
    same_points: list[InsertConvergencePoint],
    opposed_points: list[InsertConvergencePoint],
    vacuum_same_error: dict[str, float],
    vacuum_opposed_error: dict[str, float],
    superposition: dict[str, float],
    *,
    min_mesh_levels: int = 3,
    max_vacuum_field_error: float = 0.01,
    max_final_b_change: float = 0.005,
    max_final_j_change: float = 0.01,
    max_final_joule_change: float = 0.01,
    max_superposition_error: float = 1e-5,
) -> POC005GateResult:
    """Gate the first coupled dual-coil/conductor integration benchmark."""
    same_sizes, same_nodes, same_elements = _mesh_checks(same_points)
    opp_sizes, opp_nodes, opp_elements = _mesh_checks(opposed_points)
    same_b, same_j, same_loss = _final_changes(same_points)
    opp_b, opp_j, opp_loss = _final_changes(opposed_points)
    vacuum_same = float(vacuum_same_error["max_peak_normalized_complex_error"])
    vacuum_opp = float(vacuum_opposed_error["max_peak_normalized_complex_error"])
    b_super = float(superposition["b_max_peak_normalized_superposition_error"])
    j_super = float(superposition["j_max_peak_normalized_superposition_error"])

    same_finest = same_points[-1]
    opposed_finest = opposed_points[-1]
    criteria = {
        "same_minimum_mesh_levels": len(same_points) >= min_mesh_levels,
        "opposed_minimum_mesh_levels": len(opposed_points) >= min_mesh_levels,
        "same_mesh_sizes_descend": same_sizes,
        "opposed_mesh_sizes_descend": opp_sizes,
        "same_nodes_grow": same_nodes,
        "opposed_nodes_grow": opp_nodes,
        "same_elements_grow": same_elements,
        "opposed_elements_grow": opp_elements,
        "vacuum_same_matches_analytic": vacuum_same <= max_vacuum_field_error,
        "vacuum_opposed_matches_analytic": vacuum_opp <= max_vacuum_field_error,
        "same_b_converged": same_b <= max_final_b_change,
        "opposed_b_converged": opp_b <= max_final_b_change,
        "same_j_converged": same_j <= max_final_j_change,
        "opposed_j_converged": opp_j <= max_final_j_change,
        "same_joule_converged": same_loss <= max_final_joule_change,
        "opposed_joule_converged": opp_loss <= max_final_joule_change,
        "same_joule_positive": same_finest.joule_loss_w > 0.0,
        "opposed_joule_positive": opposed_finest.joule_loss_w > 0.0,
        "field_superposition": b_super <= max_superposition_error,
        "current_superposition": j_super <= max_superposition_error,
    }
    observed: dict[str, float | int] = {
        "same_mesh_levels": len(same_points),
        "opposed_mesh_levels": len(opposed_points),
        "same_finest_nodes": same_finest.node_count,
        "same_finest_elements": same_finest.element_count,
        "opposed_finest_nodes": opposed_finest.node_count,
        "opposed_finest_elements": opposed_finest.element_count,
        "vacuum_same_max_peak_normalized_field_error": vacuum_same,
        "vacuum_opposed_max_peak_normalized_field_error": vacuum_opp,
        "same_final_b_peak_normalized_change": same_b,
        "opposed_final_b_peak_normalized_change": opp_b,
        "same_final_j_peak_normalized_change": same_j,
        "opposed_final_j_peak_normalized_change": opp_j,
        "same_final_joule_relative_change": same_loss,
        "opposed_final_joule_relative_change": opp_loss,
        "same_finest_joule_loss_w": same_finest.joule_loss_w,
        "opposed_finest_joule_loss_w": opposed_finest.joule_loss_w,
        "b_superposition_error": b_super,
        "j_superposition_error": j_super,
    }
    tolerances: dict[str, float | int] = {
        "min_mesh_levels": min_mesh_levels,
        "max_vacuum_field_error": max_vacuum_field_error,
        "max_final_b_change": max_final_b_change,
        "max_final_j_change": max_final_j_change,
        "max_final_joule_change": max_final_joule_change,
        "max_superposition_error": max_superposition_error,
    }
    return POC005GateResult(
        passed=all(criteria.values()),
        criteria=criteria,
        observed=observed,
        tolerances=tolerances,
    )
