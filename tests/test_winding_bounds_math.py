import math

from pvl.geometry.bounds import component_bounds
from pvl.geometry.rig_manifest import GeometryComponent, RigShape


def test_axis_aligned_winding_extent_math():
    item = GeometryComponent(
        component_id="ring",
        shape=RigShape.WINDING_ENVELOPE,
        material_id=None,
        center_m=(0.1, 0.0, 0.0),
        axis=(1.0, 0.0, 0.0),
        parameters_m={"mean_radius": 0.05, "radial_thickness": 0.01, "axial_length": 0.02},
    )
    result = component_bounds(item)
    assert math.isclose(result.minimum_m[0], 0.09)
    assert math.isclose(result.maximum_m[0], 0.11)
    assert math.isclose(result.maximum_m[1], 0.055)
