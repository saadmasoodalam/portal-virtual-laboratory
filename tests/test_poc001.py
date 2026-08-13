import math
from pathlib import Path

import numpy as np

from pvl.core.models import POC001Config
from pvl.core.physics import MU0, circular_coil_on_axis_b_t
from pvl.geometry.poc001 import render_axisymmetric_gmsh_geo, render_gmsh_geo
from pvl.solvers.getdp.poc001 import render_magnetostatic_pro
from pvl.solvers.getdp.poc001_run import parse_getdp_axis_table
from pvl.validation.poc001 import analytical_reference, compare_fem_to_analytic


def test_center_field_matches_closed_form():
    radius = 0.05
    turns = 100
    current = 1.0
    actual = circular_coil_on_axis_b_t(0.0, radius_m=radius, turns=turns, current_a=current)
    expected = MU0 * turns * current / (2 * radius)
    assert math.isclose(actual, expected, rel_tol=1e-14)


def test_field_is_symmetric_about_coil_plane():
    z = np.array([-0.1, -0.05, 0.05, 0.1])
    b = circular_coil_on_axis_b_t(z, radius_m=0.05, turns=100, current_a=1.0)
    assert np.allclose(b[:2], b[:1:-1])


def test_hash_is_deterministic_and_sensitive():
    a = POC001Config()
    same = POC001Config()
    changed = POC001Config(coil={"radius_m": 0.06, "turns": 100, "current_a": 1.0})
    assert a.configuration_hash() == same.configuration_hash()
    assert a.configuration_hash() != changed.configuration_hash()


def test_geo_contains_required_physical_groups():
    text = render_gmsh_geo(POC001Config())
    assert 'Physical Volume("air", 1)' in text
    assert 'Physical Curve("coil", 101)' in text


def test_axisymmetric_geo_has_conformal_air_coil_regions():
    text = render_axisymmetric_gmsh_geo(POC001Config())
    assert 'Physical Surface("Air", 1)' in text
    assert 'Physical Surface("Coil", 2)' in text
    assert 'Physical Curve("Boundary", 10)' in text
    assert "Plane Surface(30) = {20, 21};" in text
    assert "Plane Surface(31) = {21};" in text


def test_getdp_model_is_axisymmetric_established_physics_only():
    text = render_magnetostatic_pro(POC001Config())
    assert "Jacobian VolAxi" in text
    assert "Magnetostatics_a_2D" in text
    assert "curl(nu curl a) = js" in text
    assert "Portal Hypothesis" not in text


def test_getdp_table_parser_extracts_y_and_by(tmp_path: Path):
    path = tmp_path / "axis.txt"
    # Synthetic Table rows: type id x y z aux aux aux Bx By Bz
    path.write_text(
        "2 1 1e-5 -0.1 0 0 0 0 1 2 3\n"
        "2 2 1e-5 0.0 0 0 0 0 4 5 6\n",
        encoding="utf-8",
    )
    y, by = parse_getdp_axis_table(path)
    assert np.allclose(y, [-0.1, 0.0])
    assert np.allclose(by, [2.0, 5.0])


def test_exact_candidate_has_zero_comparison_error():
    ref = analytical_reference(POC001Config())
    metrics = compare_fem_to_analytic(ref, np.copy(ref.b_t))
    assert metrics["max_relative_error"] == 0.0
    assert metrics["mean_relative_error"] == 0.0
    assert metrics["rms_relative_error"] == 0.0
