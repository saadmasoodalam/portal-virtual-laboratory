from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pvl.rig.measurements import CoordinateMeasurement, CountMeasurement, LengthMeasurement


class Position3D(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x: CoordinateMeasurement = Field(default_factory=CoordinateMeasurement)
    y: CoordinateMeasurement = Field(default_factory=CoordinateMeasurement)
    z: CoordinateMeasurement = Field(default_factory=CoordinateMeasurement)


class Direction3D(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x: float
    y: float
    z: float

    @model_validator(mode="after")
    def nonzero(self) -> "Direction3D":
        if self.x * self.x + self.y * self.y + self.z * self.z <= 0.0:
            raise ValueError("direction vector must be nonzero")
        return self


class FrameGeometry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    material_id: str = "mild_steel_linear_baseline"
    # Compatibility semantics retained by PVL-2O:
    # outer_width = top-view X span; outer_depth = top-view Y span;
    # outer_height = declared Z envelope; member_thickness = actual bar Z extrusion.
    outer_width: LengthMeasurement = Field(default_factory=LengthMeasurement)
    outer_depth: LengthMeasurement = Field(default_factory=LengthMeasurement)
    outer_height: LengthMeasurement = Field(default_factory=LengthMeasurement)
    member_width: LengthMeasurement = Field(default_factory=LengthMeasurement)
    member_thickness: LengthMeasurement = Field(default_factory=LengthMeasurement)


class BoundaryGapSide(StrEnum):
    """Top-view side containing the deliberate copper-boundary opening.

    The Rig v1 source specifies a deliberate gap but not which side contains it. EAST is the
    PVL exploratory default so that the choice is explicit, serialized and hashed rather than
    hidden in constructive geometry code.
    """

    NORTH = "north"
    SOUTH = "south"
    EAST = "east"
    WEST = "west"


class BoundaryGeometry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    material_id: str = "copper_baseline"
    outer_width: LengthMeasurement = Field(default_factory=LengthMeasurement)
    outer_depth: LengthMeasurement = Field(default_factory=LengthMeasurement)
    strip_width: LengthMeasurement = Field(default_factory=LengthMeasurement)
    thickness: LengthMeasurement = Field(default_factory=LengthMeasurement)
    gap_width: LengthMeasurement = Field(default_factory=LengthMeasurement)
    gap_side: BoundaryGapSide = BoundaryGapSide.EAST
    electrically_isolated_from_frame: bool = True
    baseline_open_loop: bool = True


class ChamberGeometry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    wall_material_id: str = "borosilicate_glass_baseline"
    medium_material_id: str = "air_baseline"
    center: Position3D = Field(default_factory=Position3D)
    outer_radius: LengthMeasurement = Field(default_factory=LengthMeasurement)
    wall_thickness: LengthMeasurement = Field(default_factory=LengthMeasurement)
    fill_height: LengthMeasurement = Field(default_factory=LengthMeasurement)


class CoilGeometry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    coil_id: str
    conductor_material_id: str = "copper_baseline"
    center: Position3D = Field(default_factory=Position3D)
    axis: Direction3D
    mean_radius: LengthMeasurement = Field(default_factory=LengthMeasurement)
    axial_length: LengthMeasurement = Field(default_factory=LengthMeasurement)
    radial_thickness: LengthMeasurement = Field(default_factory=LengthMeasurement)
    turns: CountMeasurement = Field(default_factory=CountMeasurement)


class SensorKind(StrEnum):
    MAGNETIC = "magnetic"
    TEMPERATURE = "temperature"
    PICKUP = "pickup"
    AMBIENT = "ambient"


class SensorDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sensor_id: str
    kind: SensorKind
    position: Position3D = Field(default_factory=Position3D)
    axis: Direction3D | None = None
