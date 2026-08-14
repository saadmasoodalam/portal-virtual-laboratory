from __future__ import annotations

from pvl.geometry.constructive import compile_constructive_topology
from pvl.geometry.exploratory import architecture_example_rig_v1
from pvl.geometry.gmsh_rig import RigGmshConfig, render_complete_rig_geo


def _graded_geo(air_margin_fraction: float) -> str:
    topology = compile_constructive_topology(architecture_example_rig_v1())
    text, _ = render_complete_rig_geo(
        topology,
        RigGmshConfig(
            characteristic_length_m=0.012,
            minimum_characteristic_length_m=0.001,
            air_margin_fraction=air_margin_fraction,
            air_min_margin_m=0.05,
            winding_characteristic_length_m=0.002,
            steel_characteristic_length_m=0.005,
            far_field_characteristic_length_m=0.040,
            far_field_near_margin_fraction=0.25,
            far_field_transition_m=0.10,
        ),
    )
    return text


def test_graded_far_field_accepts_smallest_retained_outer_domain_with_absolute_air_padding():
    # CI run #154 exposed a thin-axis corner case: the 50 mm minimum outer-air padding was
    # incorrectly reused for the inner grading box, making the two boxes coincide on that axis.
    text = _graded_geo(0.50)
    assert "Field[1] = Box;" in text
    assert "Background Field = 1;" in text


def test_graded_far_field_near_box_is_identical_across_retained_domain_sequence():
    field_lines = []
    for margin in (0.50, 0.75, 1.00):
        text = _graded_geo(margin)
        field_lines.append(
            tuple(line for line in text.splitlines() if line.startswith("Field[1]."))
        )
    assert field_lines[0] == field_lines[1] == field_lines[2]
