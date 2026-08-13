from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np

from pvl.core.models import MeshConfig
from pvl.core.poc004_models import POC004Config
from pvl.geometry.poc004 import write_gmsh_geo
from pvl.solvers.getdp.poc001_run import parse_msh2_counts
from pvl.solvers.getdp.poc004 import write_magnetoquasistatic_pro
from pvl.solvers.getdp.runner import (
    ExecutableSet,
    discover_executables,
    generate_mesh,
    run_getdp,
    solver_versions,
)
from pvl.validation.poc004 import (
    analytical_slab_reference,
    complex_peak_normalized_error,
    skin_depth_m,
)


@dataclass(frozen=True)
class SlabFEMResult:
    x_m: np.ndarray
    vector_potential_t_m: np.ndarray
    magnetic_flux_density_t: np.ndarray
    induced_current_density_a_m2: np.ndarray
    metrics: dict[str, float]
    node_count: int
    element_count: int
    mesh_file: Path


@dataclass(frozen=True)
class SlabConvergencePoint:
    characteristic_length_m: float
    metrics: dict[str, float]
    vector_potential_t_m: tuple[complex, ...]
    node_count: int
    element_count: int


@dataclass(frozen=True)
class POC004GateResult:
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


def parse_getdp_scalar_line_table(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Parse x and a real scalar from GetDP's ``Format Table`` line output."""
    x_values: list[float] = []
    field_values: list[float] = []
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            values = [float(token) for token in line.replace(",", " ").split()]
        except ValueError:
            continue
        if len(values) < 5:
            continue
        x_values.append(values[2])
        field_values.append(values[-1])
    if not x_values:
        raise ValueError(f"No scalar line samples found in GetDP table: {path}")
    x = np.asarray(x_values, dtype=float)
    field = np.asarray(field_values, dtype=float)
    order = np.argsort(x)
    return x[order], field[order]


def _load_complex_line(output_dir: Path, stem: str) -> tuple[np.ndarray, np.ndarray]:
    x_re, re = parse_getdp_scalar_line_table(output_dir / f"{stem}_re.txt")
    x_im, im = parse_getdp_scalar_line_table(output_dir / f"{stem}_im.txt")
    if not np.allclose(x_re, x_im, rtol=0.0, atol=1e-14):
        raise ValueError(f"real and imaginary {stem} sample coordinates do not match")
    return x_re, re + 1j * im


def _interpolate_complex(x_raw: np.ndarray, values: np.ndarray, x_target: np.ndarray) -> np.ndarray:
    re = np.interp(x_target, x_raw, np.real(values))
    im = np.interp(x_target, x_raw, np.imag(values))
    return re + 1j * im


def run_conducting_slab(
    config: POC004Config,
    output_dir: Path,
    *,
    executables: ExecutableSet | None = None,
) -> SlabFEMResult:
    """Mesh, solve and validate one frequency-domain magnetic-diffusion slab case."""
    exe = executables or discover_executables()
    output_dir.mkdir(parents=True, exist_ok=True)

    geo = write_gmsh_geo(config, output_dir / "poc004.geo")
    pro = write_magnetoquasistatic_pro(config, output_dir / "poc004.pro")
    mesh = generate_mesh(
        geo,
        dimension=2,
        output_path=output_dir / "poc004.msh",
        executables=exe,
    )
    nodes, elements = parse_msh2_counts(mesh)
    run = run_getdp(
        pro,
        mesh,
        resolution="MQ",
        post_operation="Line",
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

    raw_x, raw_a = _load_complex_line(output_dir, "a")
    raw_x_b, raw_b = _load_complex_line(output_dir, "by")
    raw_x_j, raw_j = _load_complex_line(output_dir, "jz")
    if not np.allclose(raw_x, raw_x_b, rtol=0.0, atol=1e-14):
        raise ValueError("A and B line coordinates do not match")
    if not np.allclose(raw_x, raw_x_j, rtol=0.0, atol=1e-14):
        raise ValueError("A and J line coordinates do not match")

    target_x = np.asarray(config.probe_x_m, dtype=float)
    fem_a = _interpolate_complex(raw_x, raw_a, target_x)
    fem_b = _interpolate_complex(raw_x, raw_b, target_x)
    fem_j = _interpolate_complex(raw_x, raw_j, target_x)
    reference = analytical_slab_reference(config)

    a_metrics = complex_peak_normalized_error(reference.vector_potential_t_m, fem_a)
    b_metrics = complex_peak_normalized_error(reference.magnetic_flux_density_t, fem_b)
    j_metrics = complex_peak_normalized_error(reference.induced_current_density_a_m2, fem_j)
    metrics = {
        "a_max_peak_normalized_complex_error": a_metrics["max_peak_normalized_complex_error"],
        "a_rms_peak_normalized_complex_error": a_metrics["rms_peak_normalized_complex_error"],
        "b_max_peak_normalized_complex_error": b_metrics["max_peak_normalized_complex_error"],
        "b_rms_peak_normalized_complex_error": b_metrics["rms_peak_normalized_complex_error"],
        "j_max_peak_normalized_complex_error": j_metrics["max_peak_normalized_complex_error"],
        "j_rms_peak_normalized_complex_error": j_metrics["rms_peak_normalized_complex_error"],
    }

    versions = solver_versions(exe)
    payload = {
        "experiment": config.model_dump(mode="json"),
        "configuration_hash": config.configuration_hash(),
        "solver_versions": {"gmsh": versions.gmsh, "getdp": versions.getdp},
        "skin_depth_m": skin_depth_m(config),
        "mesh": {"nodes": nodes, "elements": elements},
        "probe_results": [
            {
                "x_m": float(x),
                "fem_a_re_t_m": float(a.real),
                "fem_a_im_t_m": float(a.imag),
                "reference_a_re_t_m": float(ar.real),
                "reference_a_im_t_m": float(ar.imag),
                "fem_by_re_t": float(b.real),
                "fem_by_im_t": float(b.imag),
                "reference_by_re_t": float(br.real),
                "reference_by_im_t": float(br.imag),
                "fem_jz_re_a_m2": float(j.real),
                "fem_jz_im_a_m2": float(j.imag),
                "reference_jz_re_a_m2": float(jr.real),
                "reference_jz_im_a_m2": float(jr.imag),
            }
            for x, a, ar, b, br, j, jr in zip(
                target_x,
                fem_a,
                reference.vector_potential_t_m,
                fem_b,
                reference.magnetic_flux_density_t,
                fem_j,
                reference.induced_current_density_a_m2,
            )
        ],
        "metrics": metrics,
    }
    (output_dir / "metrics.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    return SlabFEMResult(
        x_m=target_x,
        vector_potential_t_m=fem_a,
        magnetic_flux_density_t=fem_b,
        induced_current_density_a_m2=fem_j,
        metrics=metrics,
        node_count=nodes,
        element_count=elements,
        mesh_file=mesh,
    )


def run_slab_mesh_convergence(
    base_config: POC004Config,
    output_dir: Path,
    *,
    characteristic_lengths_m: tuple[float, ...] = (0.001, 0.0005, 0.00025),
    executables: ExecutableSet | None = None,
) -> list[SlabConvergencePoint]:
    if len(characteristic_lengths_m) < 2:
        raise ValueError("POC-004 convergence requires at least two mesh sizes")
    if any(a <= b for a, b in zip(characteristic_lengths_m, characteristic_lengths_m[1:])):
        raise ValueError("mesh sizes must be strictly descending from coarse to fine")

    exe = executables or discover_executables()
    points: list[SlabConvergencePoint] = []
    payload: list[dict[str, object]] = []
    previous: np.ndarray | None = None

    for index, h in enumerate(characteristic_lengths_m, start=1):
        config = base_config.model_copy(
            update={"mesh": MeshConfig(characteristic_length_m=h, order=base_config.mesh.order)}
        )
        result = run_conducting_slab(config, output_dir / f"mesh_{index:02d}", executables=exe)
        point = SlabConvergencePoint(
            characteristic_length_m=h,
            metrics=result.metrics,
            vector_potential_t_m=tuple(complex(value) for value in result.vector_potential_t_m),
            node_count=result.node_count,
            element_count=result.element_count,
        )
        points.append(point)

        current = np.asarray(point.vector_potential_t_m, dtype=complex)
        successive = None
        if previous is not None:
            scale = max(float(np.max(np.abs(current))), np.finfo(float).tiny)
            successive = float(np.max(np.abs(current - previous)) / scale)
        payload.append(
            {
                "characteristic_length_m": h,
                "nodes": point.node_count,
                "elements": point.element_count,
                "successive_a_peak_normalized_change": successive,
                **point.metrics,
            }
        )
        previous = current

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "convergence.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return points


def evaluate_poc004_gate(
    points: list[SlabConvergencePoint],
    *,
    min_mesh_levels: int = 3,
    max_a_error: float = 0.01,
    max_a_rms_error: float = 0.005,
    max_b_error: float = 0.03,
    max_j_error: float = 0.01,
    max_successive_a_change: float = 0.002,
) -> POC004GateResult:
    if not points:
        raise ValueError("POC-004 gate requires convergence points")
    sizes_descend = all(
        a.characteristic_length_m > b.characteristic_length_m for a, b in zip(points, points[1:])
    )
    nodes_grow = all(a.node_count < b.node_count for a, b in zip(points, points[1:]))
    elements_grow = all(a.element_count < b.element_count for a, b in zip(points, points[1:]))
    finest = points[-1]
    if len(points) >= 2:
        previous = np.asarray(points[-2].vector_potential_t_m, dtype=complex)
        current = np.asarray(finest.vector_potential_t_m, dtype=complex)
        scale = max(float(np.max(np.abs(current))), np.finfo(float).tiny)
        successive = float(np.max(np.abs(current - previous)) / scale)
    else:
        successive = float("inf")

    criteria = {
        "minimum_mesh_levels": len(points) >= min_mesh_levels,
        "mesh_sizes_strictly_descend": sizes_descend,
        "node_counts_strictly_grow": nodes_grow,
        "element_counts_strictly_grow": elements_grow,
        "finest_a_error_within_tolerance": finest.metrics["a_max_peak_normalized_complex_error"] <= max_a_error,
        "finest_a_rms_within_tolerance": finest.metrics["a_rms_peak_normalized_complex_error"] <= max_a_rms_error,
        "finest_b_error_within_tolerance": finest.metrics["b_max_peak_normalized_complex_error"] <= max_b_error,
        "finest_j_error_within_tolerance": finest.metrics["j_max_peak_normalized_complex_error"] <= max_j_error,
        "final_successive_a_change_within_tolerance": successive <= max_successive_a_change,
    }
    observed: dict[str, float | int] = {
        "mesh_levels": len(points),
        "finest_characteristic_length_m": finest.characteristic_length_m,
        "finest_nodes": finest.node_count,
        "finest_elements": finest.element_count,
        "finest_a_max_peak_normalized_complex_error": finest.metrics["a_max_peak_normalized_complex_error"],
        "finest_a_rms_peak_normalized_complex_error": finest.metrics["a_rms_peak_normalized_complex_error"],
        "finest_b_max_peak_normalized_complex_error": finest.metrics["b_max_peak_normalized_complex_error"],
        "finest_j_max_peak_normalized_complex_error": finest.metrics["j_max_peak_normalized_complex_error"],
        "final_successive_a_peak_normalized_change": successive,
    }
    tolerances: dict[str, float | int] = {
        "min_mesh_levels": min_mesh_levels,
        "max_a_error": max_a_error,
        "max_a_rms_error": max_a_rms_error,
        "max_b_error": max_b_error,
        "max_j_error": max_j_error,
        "max_successive_a_change": max_successive_a_change,
    }
    return POC004GateResult(
        passed=all(criteria.values()),
        criteria=criteria,
        observed=observed,
        tolerances=tolerances,
    )
