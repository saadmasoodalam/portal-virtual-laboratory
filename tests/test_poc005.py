import math
from pathlib import Path

import numpy as np

from pvl.core.models import HarmonicDriveConfig
from pvl.core.poc005_models import ConductiveInsertConfig, POC005Config
from pvl.geometry.poc005 import render_axisymmetric_gmsh_geo
from pvl.solvers.getdp.poc005 import render_magnetoquasistatic_pro
from pvl.solvers.getdp.poc005_run import (
    InsertConvergencePoint,
    InsertFEMResult,
    evaluate_poc005_gate,
    parse_getdp_global_real,
    parse_getdp_real_scalar_line,
    superposition_errors,
)


def test_poc005_default_insert_skin_depth_matches_poc004_copper_scale():
    config = POC005Config()
    assert 0.0020 < config.insert_skin_depth_m < 0.0022


def test_zero_conductivity_control_has_infinite_skin_depth():
    config = POC005Config(insert=ConductiveInsertConfig(conductivity_s_m=0.0))
    assert math.isinf(config.insert_skin_depth_m)


def test_poc005_geometry_contains_two_coils_and_separate_conductor():
    text = render_axisymmetric_gmsh_geo(POC005Config())
    assert 'Physical Surface("Air", 1)' in text
    assert 'Physical Surface("CoilA", 2)' in text
    assert 'Physical Surface("CoilB", 3)' in text
    assert 'Physical Surface("Insert", 4)' in text
    assert "Plane Surface(40) = {20, 21, 22, 23};" in text
    assert "Field[3] = Min;" in text
    assert "Background Field = 3;" in text
    assert "Mesh.ElementOrder = 1;" in text


def test_poc005_getdp_contains_phase_sources_conductivity_and_joule_loss():
    text = render_magnetoquasistatic_pro(POC005Config())
    assert "F_Cos_wt_p[]" in text
    assert "sigma[Insert] = 58000000" in text
    assert "DtDof [ sigma[] * Dof{a}, {a} ]" in text
    assert "Type Complex; Frequency Freq" in text
    assert "JouleLosses" in text
    assert "0.5 * sigma[] * SquNorm[Dt[{a}]]" in text
    assert "BF_PerpendicularEdge_2E" in text


def test_negative_omega_is_rendered_through_canonical_positive_frequency_phase():
    config = POC005Config(
        drive_b=HarmonicDriveConfig(frequency_hz=1000.0, phase_rad=0.7, omega_sign=-1)
    )
    text = render_magnetoquasistatic_pro(config)
    assert "F_Cos_wt_p[]{2. * Pi * Freq, -0.69999999999999996}" in text


def test_poc005_scalar_line_parser_can_select_axis_y_or_insert_radius(tmp_path: Path):
    path = tmp_path / "line.txt"
    path.write_text(
        "15 1 1e-5 -0.1 0 0 0 0 2.5 0\n"
        "15 2 2e-5 0.2 0 0 0 0 -3.5 0\n",
        encoding="utf-8",
    )
    x, x_value = parse_getdp_real_scalar_line(path, coordinate_column=2)
    y, y_value = parse_getdp_real_scalar_line(path, coordinate_column=3)
    assert np.allclose(x, [1e-5, 2e-5])
    assert np.allclose(x_value, [2.5, -3.5])
    assert np.allclose(y, [-0.1, 0.2])
    assert np.allclose(y_value, [2.5, -3.5])


def test_poc005_global_real_parser_uses_real_member_of_complex_pair(tmp_path: Path):
    path = tmp_path / "loss.txt"
    path.write_text("12.345 0\n", encoding="utf-8")
    assert parse_getdp_global_real(path) == 12.345


def _fem(field_scale: float, current_scale: float) -> InsertFEMResult:
    z = np.array([-0.05, 0.0, 0.05])
    r = np.array([0.012, 0.025, 0.038])
    return InsertFEMResult(
        axis_z_m=z,
        b_axis_t=field_scale * np.array([1 + 0.1j, 2 + 0.2j, 1 + 0.1j]),
        insert_r_m=r,
        j_insert_a_m2=current_scale * np.array([2 - 1j, 1 - 0.5j, 0.5 - 0.25j]),
        joule_loss_w=1.0,
        node_count=100,
        element_count=200,
        mesh_file=Path("dummy.msh"),
    )


def test_superposition_error_is_zero_for_linear_combination():
    a = _fem(1.0, 1.0)
    b = _fem(0.5, -0.25)
    combined = InsertFEMResult(
        axis_z_m=a.axis_z_m,
        b_axis_t=a.b_axis_t + b.b_axis_t,
        insert_r_m=a.insert_r_m,
        j_insert_a_m2=a.j_insert_a_m2 + b.j_insert_a_m2,
        joule_loss_w=2.0,
        node_count=100,
        element_count=200,
        mesh_file=Path("dummy.msh"),
    )
    metrics = superposition_errors(combined, a, b)
    assert metrics["b_max_peak_normalized_superposition_error"] == 0.0
    assert metrics["j_max_peak_normalized_superposition_error"] == 0.0


def _point(h: float, nodes: int, elements: int, scale: float, loss: float) -> InsertConvergencePoint:
    b = tuple(scale * complex(v, 0.1 * v) for v in (1.0, 2.0, 1.0))
    j = tuple(scale * complex(v, -0.2 * v) for v in (2.0, 1.0, 0.5))
    return InsertConvergencePoint(
        characteristic_length_m=h,
        b_axis_t=b,
        j_insert_a_m2=j,
        joule_loss_w=loss,
        node_count=nodes,
        element_count=elements,
    )


def test_poc005_gate_accepts_converged_vacuum_linear_and_loss_evidence():
    same = [
        _point(0.01, 1000, 2000, 1.003, 1.006),
        _point(0.007, 2500, 5000, 1.001, 1.002),
        _point(0.005, 6000, 12000, 1.0, 1.0),
    ]
    opposed = [
        _point(0.01, 1000, 2000, 1.003, 0.806),
        _point(0.007, 2500, 5000, 1.001, 0.802),
        _point(0.005, 6000, 12000, 1.0, 0.8),
    ]
    vacuum = {
        "max_peak_normalized_complex_error": 0.002,
        "mean_peak_normalized_complex_error": 0.001,
        "rms_peak_normalized_complex_error": 0.0015,
    }
    superposition = {
        "b_max_peak_normalized_superposition_error": 1e-8,
        "j_max_peak_normalized_superposition_error": 2e-8,
    }
    gate = evaluate_poc005_gate(same, opposed, vacuum, vacuum, superposition)
    assert gate.passed
    assert all(gate.criteria.values())


def test_poc005_gate_rejects_nonconverged_joule_loss():
    same = [
        _point(0.01, 1000, 2000, 1.003, 1.3),
        _point(0.007, 2500, 5000, 1.001, 1.2),
        _point(0.005, 6000, 12000, 1.0, 1.0),
    ]
    opposed = [
        _point(0.01, 1000, 2000, 1.003, 0.806),
        _point(0.007, 2500, 5000, 1.001, 0.802),
        _point(0.005, 6000, 12000, 1.0, 0.8),
    ]
    vacuum = {
        "max_peak_normalized_complex_error": 0.002,
        "mean_peak_normalized_complex_error": 0.001,
        "rms_peak_normalized_complex_error": 0.0015,
    }
    superposition = {
        "b_max_peak_normalized_superposition_error": 1e-8,
        "j_max_peak_normalized_superposition_error": 2e-8,
    }
    gate = evaluate_poc005_gate(same, opposed, vacuum, vacuum, superposition)
    assert not gate.passed
    assert not gate.criteria["same_joule_converged"]
