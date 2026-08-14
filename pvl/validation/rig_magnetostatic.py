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


def _probe_values(
    result: RigMagnetostaticResult, probe_y_m: tuple[float, ...]
) -> tuple[float, ...]:
    requested = np.asarray(probe_y_m, dtype=float)
    if result.probe_y_m.size != requested.size or result.probe_b_y_t.size != requested.size:
        raise ValueError("complete-Rig exact probe result is empty or inconsistent")
    if not np.allclose(result.probe_y_m, requested, rtol=0.0, atol=1e-10):
        raise ValueError("complete-Rig exact probe coordinates do not match the convergence contract")
    if not np.all(np.isfinite(result.probe_b_y_t)):
        raise ValueError("complete-Rig exact probe result contains non-finite values")
    return tuple(float(value) for value in result.probe_b_y_t)


def _point(
    result: RigMagnetostaticResult,
    mesh_config: RigGmshConfig,
    probe_y_m: tuple[float, ...],
) -> RigDcConvergencePoint:
    probes = _probe_values(result, probe_y_m)
    zero_indices = [index for index, value in enumerate(probe_y_m) if abs(value) <= 1e-14]
    if len(zero_indices) != 1:
        raise ValueError("complete-Rig convergence probe contract requires exactly one y=0 probe")
    center = probes[zero_indices[0]]
    return RigDcConvergencePoint(
        characteristic_length_m=mesh_config.characteristic_length_m,
        air_margin_fraction=mesh_config.air_margin_fraction,
        node_count=result.mesh_run.summary.node_count,
        tetrahedron_count=result.mesh_run.summary.tetrahedron_count,
        probe_b_y_t=probes,
        center_b_y_t=center,
        peak_abs_b_t=float(np.max(np.abs(result.b_y_t))),
    )


def _peak_normalized_change(
    previous: RigDcConvergencePoint, current: RigDcConvergencePoint
) -> float:
    prev = np.asarray(previous.probe_b_y_t, dtype=float)
    cur = np.asarray(current.probe_b_y_t, dtype=float)
    scale = max(float(np.max(np.abs(cur))), np.finfo(float).tiny)
    return float(np.max(np.abs(cur - prev)) / scale)


def _center_relative_change(
    previous: RigDcConvergencePoint, current: RigDcConvergencePoint
) -> float:
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
    mesh_sizes_m: tuple[float, ...] = (0.04, 0.035, 0.032),
    air_margins: tuple[float, ...] = (0.25, 0.35, 0.50),
    shared_mesh_size_m: float = 0.04,
    shared_air_margin: float = 0.35,
    minimum_mesh_size_m: float = 0.001,
    winding_mesh_size_m: float | None = None,
    steel_mesh_size_m: float | None = None,
    far_field_mesh_size_m: float | None = None,
    far_field_near_margin_fraction: float = 0.25,
    far_field_transition_m: float = 0.10,
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
    if far_field_mesh_size_m is not None:
        if far_field_mesh_size_m < max(mesh_sizes_m):
            raise ValueError("far-field mesh size must not refine any retained near-field mesh level")
        if far_field_near_margin_fraction >= min(air_margins):
            raise ValueError("far-field near margin must lie inside every retained air domain")
    if len(set(probe_y_m)) != len(probe_y_m):
        raise ValueError("complete-Rig convergence probe coordinates must be unique")
    if sum(abs(value) <= 1e-14 for value in probe_y_m) != 1:
        raise ValueError("complete-Rig convergence requires exactly one y=0 point probe")
    if not all(np.isfinite(value) for value in probe_y_m):
        raise ValueError("complete-Rig convergence probe coordinates must be finite")

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
            winding_characteristic_length_m=winding_mesh_size_m,
            steel_characteristic_length_m=steel_mesh_size_m,
            far_field_characteristic_length_m=far_field_mesh_size_m,
            far_field_near_margin_fraction=far_field_near_margin_fraction,
            far_field_transition_m=far_field_transition_m,
        )
        result = run_complete_rig_dc_magnetostatic(
            experiment,
            topology,
            materials,
            config,
            output_dir / label,
            executables=exe,
            axis_samples=101,
            probe_y_m=probe_y_m,
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
        "probe_sampling": "GetDP OnPoint exact coordinates",
        "mesh_sequence": [point.__dict__ for point in mesh_points],
        "domain_sequence": [point.__dict__ for point in domain_points],
        "local_refinement": {
            "winding_mesh_size_m": winding_mesh_size_m,
            "steel_mesh_size_m": steel_mesh_size_m,
        },
        "far_field_mesh": {
            "far_field_mesh_size_m": far_field_mesh_size_m,
            "near_margin_fraction": far_field_near_margin_fraction,
            "transition_m": far_field_transition_m,
            "near_region_invariant_across_domain_sequence": far_field_mesh_size_m is not None,
        },
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
