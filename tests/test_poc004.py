import math
from pathlib import Path

import numpy as np

from pvl.core.poc004_models import POC004Config
from pvl.geometry.poc004 import render_gmsh_geo
from pvl.solvers.getdp.poc004 import render_magnetoquasistatic_pro
from pvl.solvers.getdp.poc004_run import (
    SlabConvergencePoint,
    evaluate_poc004_gate,
    parse_getdp_scalar_line_table,
)
from pvl.validation.poc004 import (
    analytical_slab_reference,
    average_joule_power_density_w_m3,
    propagation_constant_per_m,
    skin_depth_m,
)


def test_copper_like_skin_depth_at_1khz_is_about_two_millimetres():
    config = POC004Config()
    delta = skin_depth_m(config)
    assert 0.0020 < delta < 0.0022


def test_propagation_constant_has_equal_real_and_imaginary_parts():
    config = POC004Config()
    delta = skin_depth_m(config)
    k = propagation_constant_per_m(config)
    assert math.isclose(k.real, 1.0 / delta, rel_tol=1e-14)
    assert math.isclose(k.imag, 1.0 / delta, rel_tol=1e-14)


def test_finite_slab_oracle_satisfies_dirichlet_boundaries():
    config = POC004Config()
    reference = analytical_slab_reference(config, np.array([0.0, config.length_m]))
    assert np.isclose(
        reference.vector_potential_t_m[0],
        complex(config.boundary_vector_potential_t_m, 0.0),
        rtol=1e-14,
        atol=1e-20,
    )
    assert abs(reference.vector_potential_t_m[-1]) < 1e-20
    assert np.all(np.isfinite(reference.magnetic_flux_density_t))
    assert np.all(np.isfinite(reference.induced_current_density_a_m2))


def test_joule_power_density_is_nonnegative_and_decays_into_slab():
    config = POC004Config()
    x = np.linspace(0.0, config.length_m, 25)
    reference = analytical_slab_reference(config, x)
    power = average_joule_power_density_w_m3(config, reference.vector_potential_t_m)
    assert np.all(power >= 0.0)
    assert power[0] > power[len(power) // 2] > power[-1]


def test_poc004_geometry_has_conductor_and_driven_boundaries():
    text = render_gmsh_geo(POC004Config())
    assert 'Physical Surface("Conductor", 1)' in text
    assert 'Physical Curve("Left", 10)' in text
    assert 'Physical Curve("Right", 11)' in text
    assert "Mesh.ElementOrder = 1;" in text


def test_poc004_getdp_contains_complex_conductivity_dynamics():
    text = render_magnetoquasistatic_pro(POC004Config())
    assert "DtDof [ sigma[] * Dof{a} , {a} ]" in text
    assert "Type Complex; Frequency Freq" in text
    assert "BF_PerpendicularEdge_2E" in text
    assert "Re[CompZ[{a}]]" in text
    assert "Im[CompZ[{a}]]" in text
    assert "-sigma[] * CompZ[Dt[{a}]]" in text


def test_complex_system_scalar_table_parser_uses_penultimate_value_column(tmp_path: Path):
    path = tmp_path / "scalar.txt"
    # GetDP 3.2 Format Table for an explicitly real PostProcessing scalar in a
    # complex system ends with value_real value_imag. The residual imaginary
    # component is zero; the requested scalar is therefore the penultimate column.
    path.write_text(
        "15 876 0 0 0 0 0 0 0.0001 0\n"
        "15 12 0.002 0 0 0.002 0 0 -3.25e-5 0\n",
        encoding="utf-8",
    )
    x, value = parse_getdp_scalar_line_table(path)
    assert np.allclose(x, [0.0, 0.002])
    assert np.allclose(value, [0.0001, -3.25e-5])


def _point(h: float, nodes: int, elements: int, scale: float = 1.0) -> SlabConvergencePoint:
    values = tuple(scale * complex(v, -0.1 * v) for v in (1.0, 0.6, 0.3, 0.1))
    return SlabConvergencePoint(
        characteristic_length_m=h,
        metrics={
            "a_max_peak_normalized_complex_error": 0.004,
            "a_rms_peak_normalized_complex_error": 0.002,
            "b_max_peak_normalized_complex_error": 0.01,
            "b_rms_peak_normalized_complex_error": 0.005,
            "j_max_peak_normalized_complex_error": 0.004,
            "j_rms_peak_normalized_complex_error": 0.002,
        },
        vector_potential_t_m=values,
        node_count=nodes,
        element_count=elements,
    )


def test_poc004_gate_accepts_converged_accurate_sequence():
    points = [
        _point(0.001, 300, 500, 1.0010),
        _point(0.0005, 900, 1600, 1.0004),
        _point(0.00025, 3000, 5800, 1.0),
    ]
    gate = evaluate_poc004_gate(points)
    assert gate.passed
    assert all(gate.criteria.values())


def test_poc004_gate_rejects_bad_induced_current_solution():
    points = [
        _point(0.001, 300, 500, 1.0010),
        _point(0.0005, 900, 1600, 1.0004),
        _point(0.00025, 3000, 5800, 1.0),
    ]
    finest = points[-1]
    points[-1] = SlabConvergencePoint(
        characteristic_length_m=finest.characteristic_length_m,
        metrics={**finest.metrics, "j_max_peak_normalized_complex_error": 0.02},
        vector_potential_t_m=finest.vector_potential_t_m,
        node_count=finest.node_count,
        element_count=finest.element_count,
    )
    gate = evaluate_poc004_gate(points)
    assert not gate.passed
    assert not gate.criteria["finest_j_error_within_tolerance"]
