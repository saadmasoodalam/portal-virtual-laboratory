import pytest

from pvl.geometry.constructive import compile_constructive_topology
from pvl.geometry.exploratory import architecture_example_rig_v1
from pvl.validation.rig_magnetostatic import (
    RigDcConvergencePoint,
    _validate_sensor_volume_boxes,
    evaluate_rig_dc_convergence_gate,
)


def _point(h: float, margin: float, nodes: int, tets: int, scale: float) -> RigDcConvergencePoint:
    return RigDcConvergencePoint(
        characteristic_length_m=h,
        air_margin_fraction=margin,
        node_count=nodes,
        tetrahedron_count=tets,
        probe_b_y_t=tuple(scale * value for value in (0.5, 0.8, 1.0, 0.8, 0.5)),
        center_b_y_t=scale,
        peak_abs_b_t=scale,
    )


def test_sensor_volume_boxes_are_wholly_inside_retained_material_regions():
    topology = compile_constructive_topology(architecture_example_rig_v1())
    hosts = _validate_sensor_volume_boxes(
        topology,
        (-0.060, -0.030, 0.0, 0.030, 0.060),
        half_width_m=0.002,
    )
    assert hosts == ("air", "sample_medium", "sample_medium", "sample_medium", "air")


def test_sensor_volume_guard_rejects_cube_crossing_sample_wall():
    topology = compile_constructive_topology(architecture_example_rig_v1())
    with pytest.raises(ValueError, match="sample wall/interface"):
        _validate_sensor_volume_boxes(
            topology,
            (0.030,),
            half_width_m=0.004,
        )


def test_complete_rig_convergence_gate_accepts_stabilized_mesh_and_domain_sequences():
    mesh = [
        _point(0.05, 0.35, 1800, 8000, 1.020),
        _point(0.04, 0.35, 2600, 12000, 1.010),
        _point(0.032, 0.35, 4200, 20000, 1.000),
    ]
    domain = [
        _point(0.04, 0.25, 2200, 10000, 1.040),
        _point(0.04, 0.35, 2600, 12000, 1.010),
        _point(0.04, 0.50, 3500, 16000, 1.000),
    ]
    gate = evaluate_rig_dc_convergence_gate(mesh, domain)
    assert gate.passed
    assert all(gate.criteria.values())


def test_complete_rig_convergence_gate_rejects_unstable_air_domain():
    mesh = [
        _point(0.05, 0.35, 1800, 8000, 1.020),
        _point(0.04, 0.35, 2600, 12000, 1.010),
        _point(0.032, 0.35, 4200, 20000, 1.000),
    ]
    domain = [
        _point(0.04, 0.25, 2200, 10000, 1.20),
        _point(0.04, 0.35, 2600, 12000, 1.10),
        _point(0.04, 0.50, 3500, 16000, 1.00),
    ]
    gate = evaluate_rig_dc_convergence_gate(mesh, domain)
    assert not gate.passed
    assert not gate.criteria["final_domain_probe_change_within_tolerance"]
    assert not gate.criteria["final_domain_center_change_within_tolerance"]


def test_complete_rig_convergence_gate_rejects_non_monotonic_mesh_complexity():
    mesh = [
        _point(0.05, 0.35, 1800, 8000, 1.020),
        _point(0.04, 0.35, 2600, 12000, 1.010),
        _point(0.032, 0.35, 2500, 11900, 1.000),
    ]
    domain = [
        _point(0.04, 0.25, 2200, 10000, 1.020),
        _point(0.04, 0.35, 2600, 12000, 1.010),
        _point(0.04, 0.50, 3500, 16000, 1.000),
    ]
    gate = evaluate_rig_dc_convergence_gate(mesh, domain)
    assert not gate.passed
    assert not gate.criteria["mesh_node_counts_strictly_grow"]
    assert not gate.criteria["mesh_tetra_counts_strictly_grow"]
