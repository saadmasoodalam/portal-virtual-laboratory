from __future__ import annotations

from pvl.rig.components import BoundaryGapSide
from pvl.rig.measurements import MeasurementStatus
from pvl.rig.schema import RigV1Schema


EXPLORATORY_GEOMETRY_SOURCE_NOTE = (
    "PVL architecture/example geometry; exploratory simulation only, not measured hardware"
)
EXPLORATORY_UNSPECIFIED_SOURCE_NOTE = (
    "PVL exploratory topology convention for a dimension not fixed by the Rig v1 source"
)


def _length(measurement, value_m: float, *, sourced_example: bool = True) -> None:
    measurement.value_m = value_m
    measurement.status = MeasurementStatus.ILLUSTRATIVE
    measurement.source_note = (
        EXPLORATORY_GEOMETRY_SOURCE_NOTE
        if sourced_example
        else EXPLORATORY_UNSPECIFIED_SOURCE_NOTE
    )


def _coordinate(measurement, value_m: float, *, sourced_example: bool = True) -> None:
    measurement.value_m = value_m
    measurement.status = MeasurementStatus.ILLUSTRATIVE
    measurement.source_note = (
        EXPLORATORY_GEOMETRY_SOURCE_NOTE
        if sourced_example
        else EXPLORATORY_UNSPECIFIED_SOURCE_NOTE
    )


def _count(measurement, value: int, *, sourced_example: bool = True) -> None:
    measurement.value = value
    measurement.status = MeasurementStatus.ILLUSTRATIVE
    measurement.source_note = (
        EXPLORATORY_GEOMETRY_SOURCE_NOTE
        if sourced_example
        else EXPLORATORY_UNSPECIFIED_SOURCE_NOTE
    )


def architecture_example_rig_v1() -> RigV1Schema:
    """Return a complete, explicitly non-hardware-fidelity Rig v1 geometry fixture.

    Values fixed in the approved PVL architecture example are retained as illustrative data.
    Missing construction details needed by a 3D mesh (copper strip width and winding-envelope
    section) are filled with explicitly provenance-tagged exploratory conventions. Nothing in
    this fixture should be interpreted as an as-built measurement.
    """
    rig = RigV1Schema()

    # Approved PVL architecture example, mapped through the compatibility semantics frozen in 2O.
    _length(rig.frame.outer_width, 0.400)
    _length(rig.frame.outer_depth, 0.300)
    _length(rig.frame.outer_height, 0.020)
    _length(rig.frame.member_width, 0.025)
    _length(rig.frame.member_thickness, 0.020)

    _length(rig.copper_boundary.outer_width, 0.300)
    _length(rig.copper_boundary.outer_depth, 0.200)
    _length(rig.copper_boundary.strip_width, 0.010, sourced_example=False)
    _length(rig.copper_boundary.thickness, 0.001)
    _length(rig.copper_boundary.gap_width, 0.005)
    rig.copper_boundary.gap_side = BoundaryGapSide.EAST
    rig.copper_boundary.baseline_open_loop = True
    rig.copper_boundary.electrically_isolated_from_frame = True

    _coordinate(rig.sample_chamber.center.x, 0.0)
    _coordinate(rig.sample_chamber.center.y, 0.0)
    _coordinate(rig.sample_chamber.center.z, 0.0)
    _length(rig.sample_chamber.outer_radius, 0.035)
    _length(rig.sample_chamber.wall_thickness, 0.002, sourced_example=False)
    _length(rig.sample_chamber.fill_height, 0.100)

    for coil, y_m in ((rig.coil_a, -0.120), (rig.coil_b, 0.120)):
        _coordinate(coil.center.x, 0.0)
        _coordinate(coil.center.y, y_m)
        _coordinate(coil.center.z, 0.0)
        _length(coil.mean_radius, 0.040, sourced_example=False)
        # 10 mm axial length keeps the exploratory winding envelope clear of the steel frame.
        _length(coil.axial_length, 0.010, sourced_example=False)
        _length(coil.radial_thickness, 0.006, sourced_example=False)
        _count(coil.turns, 500)

    return rig
