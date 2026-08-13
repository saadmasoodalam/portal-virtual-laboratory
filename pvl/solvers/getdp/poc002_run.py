from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np

from pvl.core.models import MeshConfig, POC002Config
from pvl.geometry.poc002 import write_axisymmetric_gmsh_geo
from pvl.solvers.getdp.poc001_run import parse_getdp_axis_table, parse_msh2_counts
from pvl.solvers.getdp.poc002 import write_magnetostatic_pro
from pvl.solvers.getdp.runner import (
    ExecutableSet,
    discover_executables,
    generate_mesh,
    run_getdp,
    solver_versions,
)
from pvl.validation.poc002 import (
    compare_dual_fem,
    dual_filament_reference,
    dual_finite_source_reference,
)


@dataclass(frozen=True)
class DualFEMAxisResult:
    z_m: np.ndarray
    b_axis_t: np.ndarray
    raw_axis_file: Path
    mesh_file: Path
    metrics: dict[str, float]
    node_count: int
    element_count: int


@dataclass(frozen=True)
class DualConvergencePoint:
    characteristic_length_m: float
    metrics: dict[str, float]
    b_axis_t: tuple[float, ...]
    node_count: int
    element_count: int


@dataclass(frozen=True)
class POC002GateResult:
    passed: bool
    criteria: dict[str, bool]
    observed: dict[str, float | int | bool]
    tolerances: dict[str, float | int]

    def as_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "criteria": self.criteria,
            "observed": self.observed,
            "tolerances": self.tolerances,
        }


def _is_symmetric_pair(config: POC002Config) -> bool:
    a = config.coil_a
    b = config.coil_b
    return bool(
        np.isclose(a.radius_m, b.radius_m)
        and a.turns == b.turns
        and np.isclose(abs(a.signed_current_a), abs(b.signed_current_a))
        and np.isclose(a.center_z_m, -b.center_z_m)
    )


def _parity_metrics(config: POC002Config, z: np.ndarray, field: np.ndarray, scale: float) -> dict[str, float]:
    metrics: dict[str, float] = {}
    if not _is_symmetric_pair(config):
        return metrics
    if not np.allclose(z, -z[::-1], rtol=0.0, atol=1e-14):
        return metrics

    if np.sign(config.coil_a.signed_current_a) == np.sign(config.coil_b.signed_current_a):
        metrics["even_symmetry_peak_normalized_difference"] = float(
            np.max(np.abs(field - field[::-1])) / scale
        )
    else:
        metrics["odd_antisymmetry_peak_normalized_sum"] = float(
            np.max(np.abs(field + field[::-1])) / scale
        )
        center = np.where(np.isclose(z, 0.0, rtol=0.0, atol=1e-14))[0]
        if center.size:
            metrics["center_cancellation_peak_normalized"] = float(abs(field[center[0]]) / scale)
    return metrics


def run_axisymmetric_poc002(
    config: POC002Config,
    output_dir: Path,
    *,
    executables: ExecutableSet | None = None,
) -> DualFEMAxisResult:
    """Generate, solve and validate one independent dual-coil magnetostatic state."""
    exe = executables or discover_executables()
    output_dir.mkdir(parents=True, exist_ok=True)

    geo = write_axisymmetric_gmsh_geo(config, output_dir / "poc002_axi.geo")
    pro = write_magnetostatic_pro(config, output_dir / "poc002_axi.pro")
    mesh = generate_mesh(
        geo,
        dimension=2,
        output_path=output_dir / "poc002_axi.msh",
        executables=exe,
    )
    node_count, element_count = parse_msh2_counts(mesh)
    run = run_getdp(
        pro,
        mesh,
        resolution="Mag",
        post_operation="Axis",
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

    axis_file = output_dir / "b_axis.txt"
    if not axis_file.exists() or axis_file.stat().st_size == 0:
        raise RuntimeError("GetDP completed without producing b_axis.txt")

    raw_y, raw_by = parse_getdp_axis_table(axis_file)
    target_z = np.asarray(config.probe_z_m, dtype=float)
    fem_by = np.interp(target_z, raw_y, raw_by)

    finite_reference = dual_finite_source_reference(config)
    filament_reference = dual_filament_reference(config)
    metrics = compare_dual_fem(finite_reference, fem_by)
    scale = float(metrics["reference_peak_abs_t"])
    metrics.update(_parity_metrics(config, target_z, fem_by, scale))

    source_scale = max(float(np.max(np.abs(finite_reference.b_t))), np.finfo(float).tiny)
    source_model_difference = float(
        np.max(np.abs(finite_reference.b_t - filament_reference.b_t)) / source_scale
    )

    versions = solver_versions(exe)
    summary = {
        "experiment": config.model_dump(mode="json"),
        "configuration_hash": config.configuration_hash(),
        "solver_versions": {"gmsh": versions.gmsh, "getdp": versions.getdp},
        "mesh": {"nodes": node_count, "elements": element_count},
        "reference_model": "two finite rectangular winding sections",
        "filament_vs_finite_source_peak_normalized_difference": source_model_difference,
        "probe_results": [
            {
                "z_m": float(z),
                "fem_b_axis_t": float(fem),
                "finite_source_b_axis_t": float(finite),
                "filament_b_axis_t": float(filament),
            }
            for z, fem, finite, filament in zip(
                target_z, fem_by, finite_reference.b_t, filament_reference.b_t
            )
        ],
        "metrics": metrics,
    }
    (output_dir / "metrics.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    return DualFEMAxisResult(
        z_m=target_z,
        b_axis_t=fem_by,
        raw_axis_file=axis_file,
        mesh_file=mesh,
        metrics=metrics,
        node_count=node_count,
        element_count=element_count,
    )


def run_dual_mesh_convergence(
    base_config: POC002Config,
    output_dir: Path,
    *,
    characteristic_lengths_m: tuple[float, ...] = (0.03, 0.02, 0.012),
    executables: ExecutableSet | None = None,
) -> list[DualConvergencePoint]:
    if len(characteristic_lengths_m) < 2:
        raise ValueError("dual-coil mesh convergence requires at least two mesh sizes")
    if any(a <= b for a, b in zip(characteristic_lengths_m, characteristic_lengths_m[1:])):
        raise ValueError("mesh sizes must be strictly descending from coarse to fine")

    exe = executables or discover_executables()
    points: list[DualConvergencePoint] = []
    payload: list[dict[str, object]] = []
    previous: np.ndarray | None = None

    for index, h in enumerate(characteristic_lengths_m, start=1):
        config = base_config.model_copy(
            update={"mesh": MeshConfig(characteristic_length_m=h, order=base_config.mesh.order)}
        )
        result = run_axisymmetric_poc002(config, output_dir / f"mesh_{index:02d}", executables=exe)
        point = DualConvergencePoint(
            characteristic_length_m=h,
            metrics=result.metrics,
            b_axis_t=tuple(float(value) for value in result.b_axis_t),
            node_count=result.node_count,
            element_count=result.element_count,
        )
        points.append(point)

        current = np.asarray(point.b_axis_t, dtype=float)
        successive_change = None
        if previous is not None:
            reference_scale = max(float(point.metrics["reference_peak_abs_t"]), np.finfo(float).tiny)
            successive_change = float(np.max(np.abs(current - previous)) / reference_scale)
        payload.append(
            {
                "characteristic_length_m": h,
                "nodes": point.node_count,
                "elements": point.element_count,
                "successive_peak_normalized_field_change": successive_change,
                **point.metrics,
            }
        )
        previous = current

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "convergence.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return points


def _final_successive_change(points: list[DualConvergencePoint]) -> float:
    if len(points) < 2:
        return float("inf")
    previous = np.asarray(points[-2].b_axis_t, dtype=float)
    current = np.asarray(points[-1].b_axis_t, dtype=float)
    scale = max(float(points[-1].metrics["reference_peak_abs_t"]), np.finfo(float).tiny)
    return float(np.max(np.abs(current - previous)) / scale)


def _mesh_sequence_checks(points: list[DualConvergencePoint]) -> tuple[bool, bool, bool]:
    sizes = all(a.characteristic_length_m > b.characteristic_length_m for a, b in zip(points, points[1:]))
    nodes = all(a.node_count < b.node_count for a, b in zip(points, points[1:]))
    elements = all(a.element_count < b.element_count for a, b in zip(points, points[1:]))
    return sizes, nodes, elements


def evaluate_poc002_gate(
    same_polarity: list[DualConvergencePoint],
    opposed_polarity: list[DualConvergencePoint],
    *,
    min_mesh_levels: int = 3,
    max_peak_normalized_error: float = 0.01,
    max_rms_peak_normalized_error: float = 0.005,
    max_successive_peak_normalized_change: float = 0.001,
    max_parity_peak_normalized_error: float = 0.0001,
    max_center_cancellation_peak_normalized: float = 0.001,
) -> POC002GateResult:
    """Gate both +/+ and +/- independent-coil states before downstream PVL work."""
    if not same_polarity or not opposed_polarity:
        raise ValueError("POC-002 gate requires both same- and opposed-polarity sequences")

    same_sizes, same_nodes, same_elements = _mesh_sequence_checks(same_polarity)
    opp_sizes, opp_nodes, opp_elements = _mesh_sequence_checks(opposed_polarity)
    same_finest = same_polarity[-1]
    opp_finest = opposed_polarity[-1]

    same_max = float(same_finest.metrics["max_peak_normalized_absolute_error"])
    same_rms = float(same_finest.metrics["rms_peak_normalized_absolute_error"])
    opp_max = float(opp_finest.metrics["max_peak_normalized_absolute_error"])
    opp_rms = float(opp_finest.metrics["rms_peak_normalized_absolute_error"])
    same_parity = float(
        same_finest.metrics.get("even_symmetry_peak_normalized_difference", float("inf"))
    )
    opp_parity = float(
        opp_finest.metrics.get("odd_antisymmetry_peak_normalized_sum", float("inf"))
    )
    center_cancel = float(
        opp_finest.metrics.get("center_cancellation_peak_normalized", float("inf"))
    )
    same_successive = _final_successive_change(same_polarity)
    opp_successive = _final_successive_change(opposed_polarity)

    criteria = {
        "same_minimum_mesh_levels": len(same_polarity) >= min_mesh_levels,
        "opposed_minimum_mesh_levels": len(opposed_polarity) >= min_mesh_levels,
        "same_mesh_sizes_strictly_descend": same_sizes,
        "opposed_mesh_sizes_strictly_descend": opp_sizes,
        "same_node_counts_strictly_grow": same_nodes,
        "opposed_node_counts_strictly_grow": opp_nodes,
        "same_element_counts_strictly_grow": same_elements,
        "opposed_element_counts_strictly_grow": opp_elements,
        "same_max_error_within_tolerance": same_max <= max_peak_normalized_error,
        "opposed_max_error_within_tolerance": opp_max <= max_peak_normalized_error,
        "same_rms_error_within_tolerance": same_rms <= max_rms_peak_normalized_error,
        "opposed_rms_error_within_tolerance": opp_rms <= max_rms_peak_normalized_error,
        "same_successive_change_within_tolerance": (
            same_successive <= max_successive_peak_normalized_change
        ),
        "opposed_successive_change_within_tolerance": (
            opp_successive <= max_successive_peak_normalized_change
        ),
        "same_even_symmetry_within_tolerance": same_parity <= max_parity_peak_normalized_error,
        "opposed_odd_antisymmetry_within_tolerance": opp_parity <= max_parity_peak_normalized_error,
        "opposed_center_cancellation_within_tolerance": (
            center_cancel <= max_center_cancellation_peak_normalized
        ),
    }
    observed: dict[str, float | int | bool] = {
        "same_mesh_levels": len(same_polarity),
        "opposed_mesh_levels": len(opposed_polarity),
        "same_finest_max_peak_normalized_error": same_max,
        "opposed_finest_max_peak_normalized_error": opp_max,
        "same_finest_rms_peak_normalized_error": same_rms,
        "opposed_finest_rms_peak_normalized_error": opp_rms,
        "same_final_successive_peak_normalized_change": same_successive,
        "opposed_final_successive_peak_normalized_change": opp_successive,
        "same_even_symmetry_peak_normalized_difference": same_parity,
        "opposed_odd_antisymmetry_peak_normalized_sum": opp_parity,
        "opposed_center_cancellation_peak_normalized": center_cancel,
    }
    tolerances: dict[str, float | int] = {
        "min_mesh_levels": min_mesh_levels,
        "max_peak_normalized_error": max_peak_normalized_error,
        "max_rms_peak_normalized_error": max_rms_peak_normalized_error,
        "max_successive_peak_normalized_change": max_successive_peak_normalized_change,
        "max_parity_peak_normalized_error": max_parity_peak_normalized_error,
        "max_center_cancellation_peak_normalized": max_center_cancellation_peak_normalized,
    }
    return POC002GateResult(
        passed=all(criteria.values()),
        criteria=criteria,
        observed=observed,
        tolerances=tolerances,
    )
