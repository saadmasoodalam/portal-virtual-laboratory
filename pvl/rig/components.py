from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pvl.rig.measurements import CountMeasurement, LengthMeasurement


class Position3D(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x: LengthMeasurement = Field(default_factory=LengthMeasurement)
    y: LengthMeasurement = Field(default_factory=LengthMeasurement)
    z: LengthMeasurement = Field(default_factory=LengthMeasurement)


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
    outer_width: LengthMeasurement = Field(default_factory=LengthMeasurement)
    outer_depth: LengthMeasurement = Field(default_factory=LengthMeasurement)
    outer_height: LengthMeasurement = Field(default_factory=LengthMeasurement)
    member_width: LengthMeasurement = Field(default_factory=LengthMeasurement)
    member_thickness: LengthMeasurement = Field(default_factory=LengthMeasurement)


class BoundaryGeometry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    material_id: str = "copper_baseline"
    outer_width: LengthMeasurement = Field(default_factory=LengthMeasurement)
    outer_depth: LengthMeasurement = Field(default_factory=LengthMeasurement)
    strip_width: LengthMeasurement = Field(default_factory=LengthMeasurement)
    thickness: LengthMeasurement = Field(default_factory=LengthMeasurement)
    gap_width: LengthMeasurement = Field(default_factory=LengthMeasurement)
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
