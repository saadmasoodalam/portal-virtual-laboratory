import numpy as np

from pvl.core.models import MeshConfig, POC002Config
from pvl.geometry.poc002 import render_axisymmetric_gmsh_geo
from pvl.solvers.getdp.poc002 import render_magnetostatic_pro
from pvl.solvers.getdp.poc002_run import DualConvergencePoint, evaluate_poc002_gate
from pvl.validation.poc002 import (
    compare_dual_fem,
    dual_filament_reference,
    dual_finite_source_reference,
)


def test_same_polarity_dual_coil_reference_is_even_and_additive():
    config = POC002Config()
    reference = dual_filament_reference(config)
    assert np.all(reference.b_t > 0.0)
    assert np.allclose(reference.b_t, reference.b_t[::-1], rtol=1e-14, atol=1e-18)
    center = reference.b_t[len(reference.b_t) // 2]
    single_center_contribution = center / 2.0
    assert single_center_contribution > 0.0


def test_opposed_polarity_reference_is_odd_with_midplane_cancellation():
    same = POC002Config()
    config = same.model_copy(
        update={"coil_b": same.coil_b.model_copy(update={"polarity": -1})}
    )
    reference = dual_finite_source_reference(config, quadrature_order=32)
    assert np.allclose(reference.b_t, -reference.b_t[::-1], rtol=1e-12, atol=1e-18)
    assert abs(reference.b_t[len(reference.b_t) // 2]) < 1e-18


def test_dual_coils_are_independently_hash_sensitive():
    base = POC002Config()
    changed_a = base.model_copy(
        update={"coil_a": base.coil_a.model_copy(update={"current_a": 1.5})}
    )
    changed_b = base.model_copy(
        update={"coil_b": base.coil_b.model_copy(update={"polarity": -1})}
    )
    assert base.configuration_hash() != changed_a.configuration_hash()
    assert base.configuration_hash() != changed_b.configuration_hash()
    assert changed_a.configuration_hash() != changed_b.configuration_hash()


def test_poc002_geometry_has_two_conformal_source_regions():
    text = render_axisymmetric_gmsh_geo(POC002Config())
    assert 'Physical Surface("Air", 1)' in text
    assert 'Physical Surface("CoilA", 2)' in text
    assert 'Physical Surface("CoilB", 3)' in text
    assert "Plane Surface(30) = {20, 21, 22};" in text
    assert "Plane Surface(31) = {21};" in text
    assert "Plane Surface(32) = {22};" in text
    assert "Mesh.ElementOrder = 1;" in text


def test_poc002_getdp_renders_independent_signed_sources():
    same = POC002Config(mesh=MeshConfig(characteristic_length_m=0.02, order=2))
    opposed = same.model_copy(
        update={"coil_b": same.coil_b.model_copy(update={"polarity": -1})}
    )
    same_text = render_magnetostatic_pro(same)
    opposed_text = render_magnetostatic_pro(opposed)
    assert "CoilA = Region[2]" in same_text
    assert "CoilB = Region[3]" in same_text
    assert "BF_PerpendicularEdge_2E" in same_text
    assert "js[CoilA] = Vector[0., 0., -25000000" in same_text
    assert "js[CoilB] = Vector[0., 0., -25000000" in same_text
    assert "js[CoilB] = Vector[0., 0., 25000000" in opposed_text


def test_dual_comparison_handles_reference_zero_at_center():
    config = POC002Config()
    opposed = config.model_copy(
        update={"coil_b": config.coil_b.model_copy(update={"polarity": -1})}
    )
    reference = dual_finite_source_reference(opposed)
    metrics = compare_dual_fem(reference, np.copy(reference.b_t))
    assert metrics["max_peak_normalized_absolute_error"] == 0.0
    assert metrics["rms_peak_normalized_absolute_error"] == 0.0


def _same_point(h: float, nodes: int, elements: int, scale: float) -> DualConvergencePoint:
    return DualConvergencePoint(
        characteristic_length_m=h,
        metrics={
            "reference_peak_abs_t": 1.0,
            "max_peak_normalized_absolute_error": 0.004,
            "mean_peak_normalized_absolute_error": 0.002,
            "rms_peak_normalized_absolute_error": 0.003,
            "even_symmetry_peak_normalized_difference": 2e-6,
        },
        b_axis_t=tuple(scale * value for value in (0.4, 0.8, 1.0, 0.8, 0.4)),
        node_count=nodes,
        element_count=elements,
    )


def _opposed_point(h: float, nodes: int, elements: int, scale: float) -> DualConvergencePoint:
    return DualConvergencePoint(
        characteristic_length_m=h,
        metrics={
            "reference_peak_abs_t": 1.0,
            "max_peak_normalized_absolute_error": 0.004,
            "mean_peak_normalized_absolute_error": 0.002,
            "rms_peak_normalized_absolute_error": 0.003,
            "odd_antisymmetry_peak_normalized_sum": 2e-6,
            "center_cancellation_peak_normalized": 1e-7,
        },
        b_axis_t=tuple(scale * value for value in (-1.0, -0.5, 0.0, 0.5, 1.0)),
        node_count=nodes,
        element_count=elements,
    )


def test_poc002_gate_accepts_converged_same_and_opposed_states():
    same = [
        _same_point(0.03, 7000, 14000, 1.0005),
        _same_point(0.02, 12000, 24000, 1.0001),
        _same_point(0.012, 28000, 56000, 1.0),
    ]
    opposed = [
        _opposed_point(0.03, 7000, 14000, 1.0005),
        _opposed_point(0.02, 12000, 24000, 1.0001),
        _opposed_point(0.012, 28000, 56000, 1.0),
    ]
    gate = evaluate_poc002_gate(same, opposed)
    assert gate.passed
    assert all(gate.criteria.values())


def test_poc002_gate_rejects_failed_midplane_cancellation():
    same = [
        _same_point(0.03, 7000, 14000, 1.0005),
        _same_point(0.02, 12000, 24000, 1.0001),
        _same_point(0.012, 28000, 56000, 1.0),
    ]
    opposed = [
        _opposed_point(0.03, 7000, 14000, 1.0005),
        _opposed_point(0.02, 12000, 24000, 1.0001),
        _opposed_point(0.012, 28000, 56000, 1.0),
    ]
    bad = opposed[-1]
    opposed[-1] = DualConvergencePoint(
        characteristic_length_m=bad.characteristic_length_m,
        metrics={**bad.metrics, "center_cancellation_peak_normalized": 0.01},
        b_axis_t=bad.b_axis_t,
        node_count=bad.node_count,
        element_count=bad.element_count,
    )
    gate = evaluate_poc002_gate(same, opposed)
    assert not gate.passed
    assert not gate.criteria["opposed_center_cancellation_within_tolerance"]
