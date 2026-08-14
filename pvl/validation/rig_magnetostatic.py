from __future__ import annotations

from dataclasses import dataclass
import json
from math import sqrt
from pathlib import Path

import numpy as np

from pvl.experiments.models import ExperimentConfig
from pvl.geometry.constructive import (
    ConstructivePrimitiveKind,
    RigConstructiveTopology,
)
from pvl.geometry.gmsh_rig import RigGmshConfig, primitive_bounds
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


def _aabb_intersects(
    first: tuple[float, float, float, float, float, float],
    second: tuple[float, float, float, float, float, float],
) -> bool:
    return all(
        first[index * 2] < second[index * 2 + 1]
        and second[index * 2] < first[index * 2 + 1]
        for index in range(3)
    )


def _validate_sensor_volume_boxes(
    topology: RigConstructiveTopology,
    probe_y_m: tuple[float, ...],
    *,
    half_width_m: float,
) -> tuple[str, ...]:
    """Ensure each fixed sensor cube lies wholly in one retained material region.

    The convergence observable must not average across a material interface. The architecture fixture
    places the central three probes inside the cylindrical sample medium and the outer two in air;
    this guard derives that classification from the constructive topology rather than hard-coding it.
    A conservative AABB check then rejects overlap with every other retained material primitive.
    """
    if half_width_m <= 0.0:
        raise ValueError("sensor-volume half-width must be positive")
    medium = next(item for item in topology.primitives if item.primitive_id == "sample:medium")
    wall = next(item for item in topology.primitives if item.primitive_id == "sample:wall")
    if medium.axis != (0.0, 0.0, 1.0) or wall.axis != (0.0, 0.0, 1.0):
        raise ValueError("PVL-2Q sensor-volume guard currently requires the retained Z-axis chamber")
    medium_radius = medium.parameters_m["radius"]
    outer_radius = wall.parameters_m["outer_radius"]
    height = wall.parameters_m["height"]
    cx, cy, cz = medium.center_m
    hosts: list[str] = []

    for probe_y in probe_y_m:
        if not np.isfinite(probe_y):
            raise ValueError("sensor-volume probe centers must be finite")
        x0, x1 = cx - half_width_m, cx + half_width_m
        y0, y1 = probe_y - half_width_m, probe_y + half_width_m
        z0, z1 = cz - half_width_m, cz + half_width_m
        sensor_bounds = (x0, x1, y0, y1, z0, z1)

        dx_max = abs(cx - medium.center_m[0]) + half_width_m
        dy_max = abs(probe_y - cy) + half_width_m
        radial_max = sqrt(dx_max * dx_max + dy_max * dy_max)
        entirely_within_height = z0 >= cz - height / 2.0 and z1 <= cz + height / 2.0
        inside_medium = radial_max < medium_radius and entirely_within_height

        dx_min = max(abs(cx - wall.center_m[0]) - half_width_m, 0.0)
        dy_min = max(abs(probe_y - cy) - half_width_m, 0.0)
        radial_min = sqrt(dx_min * dx_min + dy_min * dy_min)
        outside_radially = radial_min > outer_radius
        outside_axially = z1 < cz - height / 2.0 or z0 > cz + height / 2.0
        outside_chamber = outside_radially or outside_axially

        if inside_medium:
            host = "sample_medium"
        elif outside_chamber:
            host = "air"
        else:
            raise ValueError(
                f"sensor-volume probe at y={probe_y:.17g} m intersects the sample wall/interface"
            )

        for primitive in topology.primitives:
            if primitive.kind == ConstructivePrimitiveKind.PROBE_POINT:
                continue
            if primitive.primitive_id in {"sample:medium", "sample:wall"}:
                continue
            if _aabb_intersects(sensor_bounds, primitive_bounds(primitive)):
                raise ValueError(
                    f"sensor-volume probe at y={probe_y:.17g} m overlaps {primitive.primitive_id}"
                )
        hosts.append(host)
    return tuple(hosts)


def _probe_values(
    result: RigMagnetostaticResult,
    probe_y_m: tuple[float, ...],
    *,
    use_box_probes: bool,
) -> tuple[float, ...]:
    requested = np.asarray(probe_y_m, dtype=float)
    actual_y = result.box_probe_y_m if use_box_probes else result.probe_y_m
    actual_b = result.box_probe_b_y_t if use_box_probes else result.probe_b_y_t
    label = "sensor-volume" if use_box_probes else "exact point"
    if actual_y.size != requested.size or actual_b.size != requested.size:
        raise ValueError(f"complete-Rig {label} result is empty or inconsistent")
    if not np.allclose(actual_y, requested, rtol=0.0, atol=1e-10):
        raise ValueError(f"complete-Rig {label} coordinates do not match the convergence contract")
    if not np.all(np.isfinite(actual_b)):
        raise ValueError(f"complete-Rig {label} result contains non-finite values")
    return tuple(float(value) for value in actual_b)


def _point(
    result: RigMagnetostaticResult,
    mesh_config: RigGmshConfig,
    probe_y_m: tuple[float, ...],
    *,
    use_box_probes: bool = False,
) -> RigDcConvergencePoint:
    probes = _probe_values(result, probe_y_m, use_box_probes=use_box_probes)
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
    probe_box_half_width_m: float = 0.002,
    probe_box_divisions: tuple[int, int, int] = (4, 4, 4),
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
        raise ValueError("complete-Rig convergence probe centers must be unique")
    if sum(abs(value) <= 1e-14 for value in probe_y_m) != 1:
        raise ValueError("complete-Rig convergence requires exactly one y=0 probe center")
    if not all(np.isfinite(value) for value in probe_y_m):
        raise ValueError("complete-Rig convergence probe centers must be finite")
    if len(probe_box_divisions) != 3 or any(value < 1 for value in probe_box_divisions):
        raise ValueError("sensor-volume OnBox divisions must contain three positive integers")

    probe_hosts = _validate_sensor_volume_boxes(
        topology,
        probe_y_m,
        half_width_m=probe_box_half_width_m,
    )
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
            probe_box_y_m=probe_y_m,
            probe_box_half_width_m=probe_box_half_width_m,
            probe_box_divisions=probe_box_divisions,
        )
        point = _point(result, config, probe_y_m, use_box_probes=True)
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
        "probe_sampling": (
            "fixed 3D sensor-volume B_y mean from GetDP OnBox samples using tensor trapezoidal integration"
        ),
        "probe_box_half_width_m": probe_box_half_width_m,
        "probe_box_divisions": list(probe_box_divisions),
        "probe_material_hosts": list(probe_hosts),
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
            "magnetostatic model. The 3D volume observable approximates a finite sensor active "
            "region and suppresses element-membership sensitivity without changing Maxwell's "
            "equation, source normalization, materials, boundary condition or the retained 3% gate. "
            "It is not validation against physical Rig measurements."
        ),
    }
    (output_dir / "convergence.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    return mesh_points, domain_points, gate
