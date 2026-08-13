from pvl.geometry.bounds import component_bounds
from pvl.geometry.rig_manifest import GeometryComponent, RigShape


def test_box_extent_math():
    item = GeometryComponent(
        component_id="box",
        shape=RigShape.FRAME_ENVELOPE,
        material_id=None,
        center_m=(0.0, 0.0, 0.0),
        parameters_m={"outer_width": 4.0, "outer_depth": 2.0, "outer_height": 1.0},
    )
    result = component_bounds(item)
    assert result.minimum_m == (-2.0, -1.0, -0.5)
    assert result.maximum_m == (2.0, 1.0, 0.5)
