from types import SimpleNamespace

import numpy as np
import pytest

from pvl.validation.rig_magnetostatic import (
    RigDcConvergencePoint,
    _finite_aperture_probe_values,
    _probe_sample_coordinates,
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


def test_finite_aperture_sampling_is_fixed_symmetric_and_averaged_per_probe():
    centers = (-0.03, 0.0, 0.03)
    sample_y = _probe_sample_coordinates(centers, half_width_m=0.002, samples_per_probe=5)
    assert len(sample_y) == 15
    for index, center in enumerate(centers):
        group = sample_y[index * 5 : (index + 1) * 5]
        assert group[0] == pytest.approx(center - 0.002)
        assert group[2] == pytest.approx(center)
        assert group[-1] == pytest.approx(center + 0.002)

    values = np.asarray(
        [1, 1, 1, 1, 6, 2, 2, 2, 2, 7, 3, 3, 3, 3, 8],
        dtype=float,
    )
    result = SimpleNamespace(
        probe_y_m=np.asarray(sample_y, dtype=float),
        probe_b_y_t=values,
    )
    averaged = _finite_aperture_probe_values(
        result,
        centers,
        sample_y,
        samples_per_probe=5,
    )
    assert averaged == pytest.approx((2.0, 3.0, 4.0))


def test_finite_aperture_sampling_rejects_even_sample_count():
    with pytest.raises(ValueError, match="odd sample count"):
        _probe_sample_coordinates((0.0,), half_width_m=0.002, samples_per_probe=4)


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
