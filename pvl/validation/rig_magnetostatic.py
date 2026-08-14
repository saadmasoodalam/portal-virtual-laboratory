from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np

from pvl.experiments.models import ExperimentConfig
from pvl.geometry.constructive import RigConstructiveTopology
from pvl.geometry.gmsh_rig import RigGmshConfig
from pvl.materials.library import MaterialLibrary
from pvl.solvers.getdp.rig_magnetostatic_run import (
    RigMagnetostaticResult,
    run_complete_rig_dc_magnetostatic,
)
from pvl.solvers.getdp.runner import ExecutableSet, discover_executables


@dataclass(frozen=True)
class RigDcConvergencePoint:
    characteristic_length_m: float
    air_margin_fraction: float
    node_count: int
    tetrahedron_count: int
    probe_b_y_t: tuple[float, ...]
    center_b_y_t: float
    peak_abs_b_t: float


@dataclass(frozen=True)
class RigDcConvergenceGate:
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


def _probe_values(result: RigMagnetostaticResult, probe_y_m: tuple[float, ...]) -> tuple[float, ...]:
    y = result.y_m
    b = result.b_y_t
    if any(value < y[0] or value > y[-1] for value in probe_y_m):
        raise ValueError("fixed convergence probe lies outside the solved central-axis line")
    return tuple(float(np.interp(value, y, b)) for value in probe_y_m)


def _point(
    result: RigMagnetostaticResult,
    mesh_config: RigGmshConfig,
    probe_y_m: tuple[float, ...],
) -> RigDcConvergencePoint:
    probes = _probe_values(result, probe_y_m)
    return RigDcConvergencePoint(
        characteristic_length_m=mesh_config.characteristic_length_m,
        air_margin_fraction=mesh_config.air_margin_fraction,
        node_count=result.mesh_run.summary.node_count,
        tetrahedron_count=result.mesh_run.summary.tetrahedron_count,
        probe_b_y_t=probes,
        center_b_y_t=float(np.interp(0.0, result.y_m, result.b_y_t)),
        peak_abs_b_t=float(np.max(np.abs(result.b_y_t))),
    )


def _peak_normalized_change(previous: RigDcConvergencePoint, current: RigDcConvergencePoint) -> float:
    prev = np.asarray(previous.probe_b_y_t, dtype=float)
    cur = np.asarray(current.probe_b_y_t, dtype=float)
    scale = max(float(np.max(np.abs(cur))), np.finfo(float).tiny)
    return float(np.max(np.abs(cur - prev)) / scale)


def _center_relative_change(previous: RigDcConvergencePoint, current: RigDcConvergencePoint) -> float:
    scale = max(abs(current.center_b_y_t), np.finfo(float).tiny)
    return float(abs(current.center_b_y_t - previous.center_b_y_t) / scale)


def evaluate_rig_dc_convergence_gate(
    mesh_points: list[RigDcConvergencePoint],
    domain_points: list[RigDcConvergencePoint],
    *,
    minimum_levels: int = 3,
    max_final_probe_change: float = 0.03,
    max_final_center_change: float = 0.03,
) -> RigDcConvergenceGate:
    """Gate numerical stabilization without treating a coarse exploratory solve as truth.

    The retained 3% thresholds are provisional engineering tolerances for this first complete-Rig
    linear-material validation layer. They are intentionally looser than the analytical POCs,
    because no exact full-Rig oracle exists. Passing requires stabilization under both mesh
    refinement and enlargement of the truncated air domain.
    """
    if len(mesh_points) < 2 or len(domain_points) < 2:
        raise ValueError("complete-Rig convergence gate requires at least two points per sequence")

    mesh_sizes_descend = all(
        first.characteristic_length_m > second.characteristic_length_m
        for first, second in zip(mesh_points, mesh_points[1:])
    )
    mesh_nodes_grow = all(
        first.node_count < second.node_count for first, second in zip(mesh_points, mesh_points[1:])
    )
    mesh_tets_grow = all(
        first.tetrahedron_count < second.tetrahedron_count
        for first, second in zip(mesh_points, mesh_points[1:])
    )
    domain_margins_grow = all(
        first.air_margin_fraction < second.air_margin_fraction
        for first, second in zip(domain_points, domain_points[1:])
    )

    mesh_probe_change = _peak_normalized_change(mesh_points[-2], mesh_points[-1])
    mesh_center_change = _center_relative_change(mesh_points[-2], mesh_points[-1])
    domain_probe_change = _peak_normalized_change(domain_points[-2], domain_points[-1])
    domain_center_change = _center_relative_change(domain_points[-2], domain_points[-1])
    all_nonzero = all(point.peak_abs_b_t > 0.0 for point in [*mesh_points, *domain_points])
    all_finite = all(
        np.all(np.isfinite(point.probe_b_y_t))
        and np.isfinite(point.center_b_y_t)
        and np.isfinite(point.peak_abs_b_t)
        for point in [*mesh_points, *domain_points]
    )

    criteria = {
        "minimum_mesh_levels": len(mesh_points) >= minimum_levels,
        "minimum_domain_levels": len(domain_points) >= minimum_levels,
        "mesh_sizes_strictly_descend": mesh_sizes_descend,
        "mesh_node_counts_strictly_grow": mesh_nodes_grow,
        "mesh_tetra_counts_strictly_grow": mesh_tets_grow,
        "domain_margins_strictly_grow": domain_margins_grow,
        "final_mesh_probe_change_within_tolerance": mesh_probe_change <= max_final_probe_change,
        "final_mesh_center_change_within_tolerance": mesh_center_change <= max_final_center_change,
        "final_domain_probe_change_within_tolerance": domain_probe_change <= max_final_probe_change,
        "final_domain_center_change_within_tolerance": domain_center_change <= max_final_center_change,
        "all_fields_finite": all_finite,
        "all_active_fields_nonzero": all_nonzero,
    }
    observed: dict[str, float | int] = {
        "mesh_levels": len(mesh_points),
        "domain_levels": len(domain_points),
        "finest_characteristic_length_m": mesh_points[-1].characteristic_length_m,
        "finest_nodes": mesh_points[-1].node_count,
        "finest_tetrahedra": mesh_points[-1].tetrahedron_count,
        "largest_air_margin_fraction": domain_points[-1].air_margin_fraction,
        "final_mesh_probe_peak_normalized_change": mesh_probe_change,
        "final_mesh_center_relative_change": mesh_center_change,
        "final_domain_probe_peak_normalized_change": domain_probe_change,
        "final_domain_center_relative_change": domain_center_change,
    }
    return RigDcConvergenceGate(
        passed=all(criteria.values()),
        criteria=criteria,
        observed=observed,
        tolerances={
            "minimum_levels": minimum_levels,
            "max_final_probe_change": max_final_probe_change,
            "max_final_center_change": max_final_center_change,
        },
    )


def run_rig_dc_mesh_and_domain_convergence(
    experiment: ExperimentConfig,
    topology: RigConstructiveTopology,
    materials: MaterialLibrary,
    output_dir: Path,
    *,
    # h=0.05 m was experimentally rejected by Gmsh 4.12.1 for this thin exploratory
    # topology: it emitted only a surface mesh and returned nonzero. Retain levels at and
    # below the already validated h=0.04 complete-Rig mesh instead of weakening geometry gates.
    mesh_sizes_m: tuple[float, ...] = (0.04, 0.035, 0.03),
    air_margins: tuple[float, ...] = (0.25, 0.35, 0.50),
    shared_mesh_size_m: float = 0.04,
    shared_air_margin: float = 0.35,
    minimum_mesh_size_m: float = 0.001,
    probe_y_m: tuple[float, ...] = (-0.10, -0.05, 0.0, 0.05, 0.10),
    executables: ExecutableSet | None = None,
) -> tuple[list[RigDcConvergencePoint], list[RigDcConvergencePoint], RigDcConvergenceGate]:
    if len(mesh_sizes_m) < 3 or len(air_margins) < 3:
        raise ValueError("PVL-2Q retained convergence sequences require at least three levels")
    if any(first <= second for first, second in zip(mesh_sizes_m, mesh_sizes_m[1:])):
        raise ValueError("mesh sizes must strictly descend coarse to fine")
    if any(first >= second for first, second in zip(air_margins, air_margins[1:])):
        raise ValueError("air margins must strictly increase")
    if shared_mesh_size_m not in mesh_sizes_m or shared_air_margin not in air_margins:
        raise ValueError("shared mesh/domain baseline must be present in both retained sequences")

    exe = executables or discover_executables()
    output_dir.mkdir(parents=True, exist_ok=True)
    cache: dict[tuple[float, float], RigDcConvergencePoint] = {}

    def solve(mesh_size: float, air_margin: float, label: str) -> RigDcConvergencePoint:
        key = (mesh_size, air_margin)
        if key in cache:
            return cache[key]
        config = RigGmshConfig(
            characteristic_length_m=mesh_size,
            minimum_characteristic_length_m=minimum_mesh_size_m,
            air_margin_fraction=air_margin,
        )
        result = run_complete_rig_dc_magnetostatic(
            experiment,
            topology,
            materials,
            config,
            output_dir / label,
            executables=exe,
        )
        point = _point(result, config, probe_y_m)
        cache[key] = point
        return point

    mesh_points = [
        solve(size, shared_air_margin, f"mesh_{index:02d}")
        for index, size in enumerate(mesh_sizes_m, start=1)
    ]
    domain_points: list[RigDcConvergencePoint] = []
    for index, margin in enumerate(air_margins, start=1):
        key = (shared_mesh_size_m, margin)
        if key in cache:
            point = cache[key]
        else:
            point = solve(shared_mesh_size_m, margin, f"domain_{index:02d}")
        domain_points.append(point)

    gate = evaluate_rig_dc_convergence_gate(mesh_points, domain_points)
    payload = {
        "probe_y_m": list(probe_y_m),
        "mesh_sequence": [point.__dict__ for point in mesh_points],
        "domain_sequence": [point.__dict__ for point in domain_points],
        "validation_gate": gate.as_dict(),
        "scientific_boundary": (
            "This is numerical stabilization of an exploratory linear-material complete-Rig "
            "magnetostatic model, not validation against physical Rig measurements."
        ),
    }
    (output_dir / "convergence.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    return mesh_points, domain_points, gate
