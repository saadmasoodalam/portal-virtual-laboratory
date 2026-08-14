from __future__ import annotations

import math

import pytest

from pvl.geometry.constructive import ConstructivePrimitiveKind, compile_constructive_topology
from pvl.geometry.coordinates import RIG_COORDINATE_CONVENTION_ID
from pvl.geometry.rig_compile import compile_rig_geometry
from pvl.rig.components import BoundaryGapSide
from pvl.rig.measurements import MeasurementStatus
from pvl.rig.schema import RigV1Schema


def _set_length(measurement, value: float) -> None:
    measurement.value_m = value
    measurement.status = MeasurementStatus.ILLUSTRATIVE
    measurement.source_note = "PVL-2O architecture/example topology regression"


def _set_coordinate(measurement, value: float) -> None:
    measurement.value_m = value
    measurement.status = MeasurementStatus.ILLUSTRATIVE
    measurement.source_note = "PVL-2O architecture/example topology regression"


def _set_count(measurement, value: int) -> None:
    measurement.value = value
    measurement.status = MeasurementStatus.ILLUSTRATIVE
    measurement.source_note = "PVL-2O architecture/example topology regression"


def _architecture_example_rig() -> RigV1Schema:
    rig = RigV1Schema()

    # Compatibility mapping: current schema outer_depth is the top-view Y span and
    # outer_height is the declared Z envelope. This reproduces the approved 400 x 300 mm
    # planar frame with 20 mm physical depth without renaming persisted schema fields.
    _set_length(rig.frame.outer_width, 0.400)
    _set_length(rig.frame.outer_depth, 0.300)
    _set_length(rig.frame.outer_height, 0.020)
    _set_length(rig.frame.member_width, 0.025)
    _set_length(rig.frame.member_thickness, 0.020)

    _set_length(rig.copper_boundary.outer_width, 0.300)
    _set_length(rig.copper_boundary.outer_depth, 0.200)
    _set_length(rig.copper_boundary.strip_width, 0.010)
    _set_length(rig.copper_boundary.thickness, 0.001)
    _set_length(rig.copper_boundary.gap_width, 0.005)
    rig.copper_boundary.gap_side = BoundaryGapSide.EAST
    rig.copper_boundary.baseline_open_loop = True

    for axis, value in zip((rig.sample_chamber.center.x, rig.sample_chamber.center.y, rig.sample_chamber.center.z), (0.0, 0.0, 0.0)):
        _set_coordinate(axis, value)
    _set_length(rig.sample_chamber.outer_radius, 0.035)
    _set_length(rig.sample_chamber.wall_thickness, 0.002)
    _set_length(rig.sample_chamber.fill_height, 0.100)

    for coil, y in ((rig.coil_a, -0.120), (rig.coil_b, 0.120)):
        _set_coordinate(coil.center.x, 0.0)
        _set_coordinate(coil.center.y, y)
        _set_coordinate(coil.center.z, 0.0)
        _set_length(coil.mean_radius, 0.040)
        _set_length(coil.axial_length, 0.020)
        _set_length(coil.radial_thickness, 0.010)
        _set_count(coil.turns, 500)

    return rig


def _strict_box_overlap(a, b, tol: float = 1e-12) -> bool:
    assert a.size_m is not None and b.size_m is not None
    for axis in range(3):
        a0 = a.center_m[axis] - a.size_m[axis] / 2.0
        a1 = a.center_m[axis] + a.size_m[axis] / 2.0
        b0 = b.center_m[axis] - b.size_m[axis] / 2.0
        b1 = b.center_m[axis] + b.size_m[axis] / 2.0
        if min(a1, b1) - max(a0, b0) <= tol:
            return False
    return True


def test_default_coil_geometric_normals_face_central_axis_from_opposite_y_sides():
    rig = RigV1Schema()
    assert (rig.coil_a.axis.x, rig.coil_a.axis.y, rig.coil_a.axis.z) == (0.0, 1.0, 0.0)
    assert (rig.coil_b.axis.x, rig.coil_b.axis.y, rig.coil_b.axis.z) == (0.0, -1.0, 0.0)


def test_architecture_example_compiles_four_piece_planar_steel_frame_and_explicit_open_copper_loop():
    topology = compile_constructive_topology(_architecture_example_rig())
    assert topology.coordinate_convention.convention_id == RIG_COORDINATE_CONVENTION_ID
    assert topology.frame_envelope_size_m == (0.4, 0.3, 0.02)
    assert topology.hardware_fidelity_ready is False

    steel = [p for p in topology.primitives if p.component_id == "steel_frame"]
    copper = [p for p in topology.primitives if p.component_id == "copper_boundary"]
    assert len(steel) == 4
    assert len(copper) == 5
    assert all(p.kind == ConstructivePrimitiveKind.BOX for p in steel + copper)
    assert {p.metadata["member"] for p in steel} == {"north", "south", "east", "west"}
    assert {p.metadata["member"] for p in copper} == {"north", "south", "east", "west"}

    north = next(p for p in steel if p.metadata["member"] == "north")
    east = next(p for p in steel if p.metadata["member"] == "east")
    assert north.size_m == (0.4, 0.025, 0.02)
    assert east.size_m == (0.025, 0.25, 0.02)
    assert math.isclose(north.center_m[1], 0.1375)
    assert math.isclose(east.center_m[0], 0.1875)

    east_fragments = [p for p in copper if p.metadata["member"] == "east"]
    assert len(east_fragments) == 2
    south_fragment = next(p for p in east_fragments if p.primitive_id.endswith(":south"))
    north_fragment = next(p for p in east_fragments if p.primitive_id.endswith(":north"))
    assert south_fragment.size_m is not None and north_fragment.size_m is not None
    south_edge = south_fragment.center_m[1] + south_fragment.size_m[1] / 2.0
    north_edge = north_fragment.center_m[1] - north_fragment.size_m[1] / 2.0
    assert math.isclose(north_edge - south_edge, 0.005, rel_tol=0.0, abs_tol=1e-12)


def test_frame_and_copper_piece_conventions_have_no_positive_volume_self_overlap():
    topology = compile_constructive_topology(_architecture_example_rig())
    for component_id in ("steel_frame", "copper_boundary"):
        boxes = [p for p in topology.primitives if p.component_id == component_id]
        for index, first in enumerate(boxes):
            for second in boxes[index + 1 :]:
                assert not _strict_box_overlap(first, second), (first.primitive_id, second.primitive_id)


def test_copper_must_fit_inside_open_steel_rectangle():
    rig = _architecture_example_rig()
    _set_length(rig.copper_boundary.outer_width, 0.360)
    with pytest.raises(ValueError, match="copper boundary must fit"):
        compile_constructive_topology(rig)


def test_sample_must_fit_inside_copper_inner_opening():
    rig = _architecture_example_rig()
    _set_coordinate(rig.sample_chamber.center.x, 0.120)
    with pytest.raises(ValueError, match="sample chamber exceeds.*X"):
        compile_constructive_topology(rig)


def test_copper_gap_side_is_hashed_and_changes_constructive_identity():
    east = _architecture_example_rig()
    west = _architecture_example_rig()
    west.copper_boundary.gap_side = BoundaryGapSide.WEST
    first = compile_constructive_topology(east)
    second = compile_constructive_topology(west)
    assert first.fingerprint_sha256() != second.fingerprint_sha256()
    assert first.source_rig_fingerprint != second.source_rig_fingerprint


def test_solver_neutral_manifest_carries_explicit_coordinate_and_gap_provenance():
    manifest = compile_rig_geometry(_architecture_example_rig())
    assert manifest.convention == RIG_COORDINATE_CONVENTION_ID
    frame = next(item for item in manifest.components if item.component_id == "steel_frame")
    copper = next(item for item in manifest.components if item.component_id == "copper_boundary")
    assert frame.metadata["outer_depth_semantics"] == "top_view_y_span_legacy_name"
    assert copper.metadata["gap_side"] == "east"
    assert copper.metadata["gap_side_provenance"] == "explicit_exploratory_modeling_convention"


def test_constructive_topology_is_deterministic_for_identical_rig():
    first = compile_constructive_topology(_architecture_example_rig())
    second = compile_constructive_topology(_architecture_example_rig())
    assert first.fingerprint_sha256() == second.fingerprint_sha256()
