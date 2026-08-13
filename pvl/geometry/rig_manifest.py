from enum import StrEnum
from hashlib import sha256
import json
from pydantic import BaseModel, ConfigDict, Field

class RigShape(StrEnum):
    FRAME_ENVELOPE = "frame_envelope"
    OPEN_RECTANGULAR_LOOP = "open_rectangular_loop"
    CYLINDRICAL_SHELL = "cylindrical_shell"
    CYLINDRICAL_VOLUME = "cylindrical_volume"
    WINDING_ENVELOPE = "winding_envelope"
    SENSOR_POINT = "sensor_point"

class GeometryComponent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    component_id: str
    shape: RigShape
    material_id: str | None
    center_m: tuple[float, float, float]
    axis: tuple[float, float, float] | None = None
    parameters_m: dict[str, float]
    integer_parameters: dict[str, int] = Field(default_factory=dict)
    metadata: dict[str, str | bool] = Field(default_factory=dict)

class RigGeometryManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    rig_id: str
    convention: str = "right_handed_xyz_si_m"
    components: tuple[GeometryComponent, ...]

    def fingerprint_sha256(self) -> str:
        value = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return sha256(value.encode()).hexdigest()
