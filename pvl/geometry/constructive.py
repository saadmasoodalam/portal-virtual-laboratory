from __future__ import annotations

from enum import StrEnum
from hashlib import sha256
import json
from math import sqrt

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pvl.geometry.coordinates import RIG_V1_COORDINATE_CONVENTION, RigCoordinateConvention
from pvl.rig.components import BoundaryGapSide
from pvl.rig.fingerprint import rig_definition_fingerprint
from pvl.rig.schema import RigV1Schema


CONSTRUCTIVE_TOPOLOGY_SCHEMA_VERSION = "pvl-rig-constructive-topology-v1"


class ConstructivePrimitiveKind(StrEnum):
    BOX = "box"
    CYLINDRICAL_SHELL = "cylindrical_shell"
    CYLINDRICAL_VOLUME = "cylindrical_volume"
    WINDING_ENVELOPE = "winding_envelope"
    PROBE_POINT = "probe_point"


class ConstructivePrimitive(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    primitive_id: str
    component_id: str
    kind: ConstructivePrimitiveKind
    material_id: str | None
    center_m: tuple[float, float, float]
    size_m: tuple[float, float, float] | None = None
    axis: tuple[float, float, float] | None = None
    parameters_m: dict[str, float] = Field(default_factory=dict)
    integer_parameters: dict[str, int] = Field(default_factory=dict)
    metadata: dict[str, str | bool] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_geometry(self) -> "ConstructivePrimitive":
        if self.kind == ConstructivePrimitiveKind.BOX:
            if self.size_m is None or any(value <= 0.0 for value in self.size_m):
                raise ValueError("box primitive requires three positive sizes")
        if self.kind in {
            ConstructivePrimitiveKind.CYLINDRICAL_SHELL,
            ConstructivePrimitiveKind.CYLINDRICAL_VOLUME,
            ConstructivePrimitiveKind.WINDING_ENVELOPE,
        }:
            if self.axis is None:
                raise ValueError(f"{self.kind.value} requires an axis")
            norm = sqrt(sum(value * value for value in self.axis))
            if abs(norm - 1.0) > 1e-9:
                raise ValueError("constructive primitive axis must be normalized")
        return self


class RigConstructiveTopology(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: str = CONSTRUCTIVE_TOPOLOGY_SCHEMA_VERSION
    rig_id: str
    source_rig_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    coordinate_convention: RigCoordinateConvention = RIG_V1_COORDINATE_CONVENTION
    topology_fidelity: str = "exploratory_constructive_contract"
    hardware_fidelity_ready: bool
    frame_envelope_size_m: tuple[float, float, float]
    primitives: tuple[ConstructivePrimitive, ...]
    warnings: tuple[str, ...] = ()

    def fingerprint_sha256(self) -> str:
        payload = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return sha256(payload.encode("utf-8")).hexdigest()


def _m(value, path: str) -> float:
    if value.value_m is None:
        raise ValueError(f"missing geometry value: {path}")
    result = float(value.value_m)
    if result <= 0.0:
        raise ValueError(f"geometry length must be positive: {path}")
    return result


def _position(value, path: str) -> tuple[float, float, float]:
    result: list[float] = []
    for axis in ("x", "y", "z"):
        measurement = getattr(value, axis)
        if measurement.value_m is None:
            raise ValueError(f"missing geometry value: {path}.{axis}")
        result.append(float(measurement.value_m))
    return tuple(result)  # type: ignore[return-value]


def _axis(value) -> tuple[float, float, float]:
    norm = sqrt(value.x * value.x + value.y * value.y + value.z * value.z)
    return (value.x / norm, value.y / norm, value.z / norm)


def _box(
    primitive_id: str,
    component_id: str,
    material_id: str,
    center: tuple[float, float, float],
    size: tuple[float, float, float],
    **metadata: str | bool,
) -> ConstructivePrimitive:
    return ConstructivePrimitive(
        primitive_id=primitive_id,
        component_id=component_id,
        kind=ConstructivePrimitiveKind.BOX,
        material_id=material_id,
        center_m=center,
        size_m=size,
        metadata=metadata,
    )


def _frame_members(rig: RigV1Schema) -> tuple[list[ConstructivePrimitive], list[str]]:
    frame = rig.frame
    width = _m(frame.outer_width, "frame.outer_width")
    depth = _m(frame.outer_depth, "frame.outer_depth")
    declared_height = _m(frame.outer_height, "frame.outer_height")
    member_width = _m(frame.member_width, "frame.member_width")
    thickness = _m(frame.member_thickness, "frame.member_thickness")
    if 2.0 * member_width >= min(width, depth):
        raise ValueError("frame member width leaves no open central rectangle")
    if thickness > declared_height + 1e-12:
        raise ValueError("frame member thickness exceeds declared frame Z envelope")

    half_x = width / 2.0 - member_width / 2.0
    half_y = depth / 2.0 - member_width / 2.0
    interior_y = depth - 2.0 * member_width
    pieces = [
        _box("steel:north", "steel_frame", frame.material_id, (0.0, half_y, 0.0), (width, member_width, thickness), member="north"),
        _box("steel:south", "steel_frame", frame.material_id, (0.0, -half_y, 0.0), (width, member_width, thickness), member="south"),
        _box("steel:east", "steel_frame", frame.material_id, (half_x, 0.0, 0.0), (member_width, interior_y, thickness), member="east"),
        _box("steel:west", "steel_frame", frame.material_id, (-half_x, 0.0, 0.0), (member_width, interior_y, thickness), member="west"),
    ]
    warnings = [
        "Steel corner joints use an overlap-free butt-joint idealization; Rig v1 source material does not specify measured joint geometry."
    ]
    if declared_height > thickness + 1e-12:
        warnings.append(
            "frame.outer_height exceeds member_thickness; constructive steel uses member_thickness as the physical Z extrusion and preserves outer_height only as the declared envelope."
        )
    return pieces, warnings


def _copper_members(rig: RigV1Schema) -> tuple[list[ConstructivePrimitive], list[str]]:
    boundary = rig.copper_boundary
    width = _m(boundary.outer_width, "copper_boundary.outer_width")
    depth = _m(boundary.outer_depth, "copper_boundary.outer_depth")
    strip = _m(boundary.strip_width, "copper_boundary.strip_width")
    thickness = _m(boundary.thickness, "copper_boundary.thickness")
    gap = _m(boundary.gap_width, "copper_boundary.gap_width")
    if 2.0 * strip >= min(width, depth):
        raise ValueError("copper strip width leaves no open central rectangle")
    if not boundary.electrically_isolated_from_frame:
        raise ValueError("Rig v1 copper boundary must remain electrically isolated from the steel frame")

    inner_y = depth - 2.0 * strip
    x_side = width / 2.0 - strip / 2.0
    y_side = depth / 2.0 - strip / 2.0
    side = boundary.gap_side
    is_open = boundary.baseline_open_loop
    pieces: list[ConstructivePrimitive] = []

    def horizontal(name: str, y: float, gap_here: bool) -> None:
        if not gap_here:
            pieces.append(_box(f"copper:{name}", "copper_boundary", boundary.material_id, (0.0, y, 0.0), (width, strip, thickness), member=name))
            return
        if gap >= width:
            raise ValueError("copper gap must be smaller than the selected horizontal side")
        segment = (width - gap) / 2.0
        offset = gap / 2.0 + segment / 2.0
        pieces.extend([
            _box(f"copper:{name}:west", "copper_boundary", boundary.material_id, (-offset, y, 0.0), (segment, strip, thickness), member=name, gap_fragment=True),
            _box(f"copper:{name}:east", "copper_boundary", boundary.material_id, (offset, y, 0.0), (segment, strip, thickness), member=name, gap_fragment=True),
        ])

    def vertical(name: str, x: float, gap_here: bool) -> None:
        if not gap_here:
            pieces.append(_box(f"copper:{name}", "copper_boundary", boundary.material_id, (x, 0.0, 0.0), (strip, inner_y, thickness), member=name))
            return
        if gap >= inner_y:
            raise ValueError("copper gap must be smaller than the selected vertical side between corner strips")
        segment = (inner_y - gap) / 2.0
        offset = gap / 2.0 + segment / 2.0
        pieces.extend([
            _box(f"copper:{name}:south", "copper_boundary", boundary.material_id, (x, -offset, 0.0), (strip, segment, thickness), member=name, gap_fragment=True),
            _box(f"copper:{name}:north", "copper_boundary", boundary.material_id, (x, offset, 0.0), (strip, segment, thickness), member=name, gap_fragment=True),
        ])

    horizontal("north", y_side, is_open and side == BoundaryGapSide.NORTH)
    horizontal("south", -y_side, is_open and side == BoundaryGapSide.SOUTH)
    vertical("east", x_side, is_open and side == BoundaryGapSide.EAST)
    vertical("west", -x_side, is_open and side == BoundaryGapSide.WEST)
    warnings = [
        f"Copper gap side '{side.value}' is an explicit PVL modeling convention because the Rig v1 source specifies a deliberate gap but not its side."
    ]
    return pieces, warnings


def _validate_nested_planar_geometry(rig: RigV1Schema) -> None:
    frame = rig.frame
    boundary = rig.copper_boundary
    frame_width = _m(frame.outer_width, "frame.outer_width")
    frame_depth = _m(frame.outer_depth, "frame.outer_depth")
    member = _m(frame.member_width, "frame.member_width")
    copper_width = _m(boundary.outer_width, "copper_boundary.outer_width")
    copper_depth = _m(boundary.outer_depth, "copper_boundary.outer_depth")
    frame_inner_width = frame_width - 2.0 * member
    frame_inner_depth = frame_depth - 2.0 * member
    if copper_width > frame_inner_width + 1e-12 or copper_depth > frame_inner_depth + 1e-12:
        raise ValueError("copper boundary must fit inside the open steel-frame rectangle")

    strip = _m(boundary.strip_width, "copper_boundary.strip_width")
    copper_inner_width = copper_width - 2.0 * strip
    copper_inner_depth = copper_depth - 2.0 * strip
    chamber = rig.sample_chamber
    center = _position(chamber.center, "sample_chamber.center")
    radius = _m(chamber.outer_radius, "sample_chamber.outer_radius")
    if abs(center[0]) + radius > copper_inner_width / 2.0 + 1e-12:
        raise ValueError("sample chamber exceeds copper-boundary inner opening in X")
    if abs(center[1]) + radius > copper_inner_depth / 2.0 + 1e-12:
        raise ValueError("sample chamber exceeds copper-boundary inner opening in Y")


def compile_constructive_topology(rig: RigV1Schema) -> RigConstructiveTopology:
    """Compile a solver-oriented topology contract without generating a Gmsh model.

    This is deliberately exploratory. It turns the Rig v1 top-view engineering definition into
    explicit non-overlapping primitives while preserving unresolved hardware joint/gap provenance.
    """
    readiness = rig.readiness_report()
    if not readiness.computational_ready:
        raise ValueError("Rig geometry contains unknown required measurements")
    _validate_nested_planar_geometry(rig)

    frame_pieces, warnings = _frame_members(rig)
    copper_pieces, copper_warnings = _copper_members(rig)
    warnings.extend(copper_warnings)
    primitives: list[ConstructivePrimitive] = [*frame_pieces, *copper_pieces]

    chamber = rig.sample_chamber
    center = _position(chamber.center, "sample_chamber.center")
    outer_radius = _m(chamber.outer_radius, "sample_chamber.outer_radius")
    wall = _m(chamber.wall_thickness, "sample_chamber.wall_thickness")
    height = _m(chamber.fill_height, "sample_chamber.fill_height")
    if wall >= outer_radius:
        raise ValueError("sample chamber wall must be smaller than its outer radius")
    primitives.extend([
        ConstructivePrimitive(
            primitive_id="sample:wall",
            component_id="sample_chamber_wall",
            kind=ConstructivePrimitiveKind.CYLINDRICAL_SHELL,
            material_id=chamber.wall_material_id,
            center_m=center,
            axis=(0.0, 0.0, 1.0),
            parameters_m={"outer_radius": outer_radius, "wall_thickness": wall, "height": height},
        ),
        ConstructivePrimitive(
            primitive_id="sample:medium",
            component_id="sample_medium",
            kind=ConstructivePrimitiveKind.CYLINDRICAL_VOLUME,
            material_id=chamber.medium_material_id,
            center_m=center,
            axis=(0.0, 0.0, 1.0),
            parameters_m={"radius": outer_radius - wall, "height": height},
        ),
    ])

    for name, coil in (("coil_a", rig.coil_a), ("coil_b", rig.coil_b)):
        if coil.turns.value is None or coil.turns.value <= 0:
            raise ValueError(f"missing or invalid geometry value: {name}.turns")
        primitives.append(ConstructivePrimitive(
            primitive_id=f"winding:{name}",
            component_id=name,
            kind=ConstructivePrimitiveKind.WINDING_ENVELOPE,
            material_id=coil.conductor_material_id,
            center_m=_position(coil.center, f"{name}.center"),
            axis=_axis(coil.axis),
            parameters_m={
                "mean_radius": _m(coil.mean_radius, f"{name}.mean_radius"),
                "axial_length": _m(coil.axial_length, f"{name}.axial_length"),
                "radial_thickness": _m(coil.radial_thickness, f"{name}.radial_thickness"),
            },
            integer_parameters={"turns": int(coil.turns.value)},
            metadata={"axis_is_geometric_normal_not_field_polarity": True},
        ))

    for sensor in rig.sensors:
        primitives.append(ConstructivePrimitive(
            primitive_id=f"probe:{sensor.sensor_id}",
            component_id=f"sensor:{sensor.sensor_id}",
            kind=ConstructivePrimitiveKind.PROBE_POINT,
            material_id=None,
            center_m=_position(sensor.position, f"sensor:{sensor.sensor_id}"),
            axis=_axis(sensor.axis) if sensor.axis else None,
            metadata={"sensor_kind": sensor.kind.value},
        ))

    frame_size = (
        _m(rig.frame.outer_width, "frame.outer_width"),
        _m(rig.frame.outer_depth, "frame.outer_depth"),
        _m(rig.frame.outer_height, "frame.outer_height"),
    )
    return RigConstructiveTopology(
        rig_id=rig.rig_id,
        source_rig_fingerprint=rig_definition_fingerprint(rig),
        hardware_fidelity_ready=readiness.hardware_fidelity_ready,
        frame_envelope_size_m=frame_size,
        primitives=tuple(primitives),
        warnings=tuple(warnings),
    )
