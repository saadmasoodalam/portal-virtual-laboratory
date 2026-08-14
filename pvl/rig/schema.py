from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from pvl.rig.components import BoundaryGeometry, ChamberGeometry, CoilGeometry, Direction3D, FrameGeometry, SensorDefinition
from pvl.rig.measurements import CoordinateMeasurement, CountMeasurement, LengthMeasurement


class ReadinessReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    computational_ready: bool
    hardware_fidelity_ready: bool
    missing_required_measurements: tuple[str, ...]
    non_fidelity_measurements: tuple[str, ...]


def _items(value: Any, path: str = "") -> list[tuple[str, object]]:
    if isinstance(value, (CoordinateMeasurement, LengthMeasurement, CountMeasurement)):
        return [(path, value)]
    result: list[tuple[str, object]] = []
    if isinstance(value, BaseModel):
        for name in value.__class__.model_fields:
            next_path = f"{path}.{name}" if path else name
            result.extend(_items(getattr(value, name), next_path))
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            result.extend(_items(child, f"{path}[{index}]"))
    return result


class RigV1Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rig_id: str = "portal_boundary_physics_rig_v1"
    ambient_material_id: str = "air_baseline"
    frame: FrameGeometry = Field(default_factory=FrameGeometry)
    copper_boundary: BoundaryGeometry = Field(default_factory=BoundaryGeometry)
    sample_chamber: ChamberGeometry = Field(default_factory=ChamberGeometry)
    # Rig v1 top view places the coils on opposite Y sides of the central chamber.
    # Their geometric normals point toward the center by default. Electrical polarity remains
    # an independent experiment variable and must not be inferred from this axis sign.
    coil_a: CoilGeometry = Field(default_factory=lambda: CoilGeometry(coil_id="A", axis=Direction3D(x=0.0, y=1.0, z=0.0)))
    coil_b: CoilGeometry = Field(default_factory=lambda: CoilGeometry(coil_id="B", axis=Direction3D(x=0.0, y=-1.0, z=0.0)))
    sensors: list[SensorDefinition] = Field(default_factory=list)

    def readiness_report(self) -> ReadinessReport:
        missing: list[str] = []
        low_fidelity: list[str] = []
        for path, item in _items(self):
            if not item.required_for_solver:
                continue
            if not item.has_value:
                missing.append(path)
            elif not item.is_hardware_fidelity:
                low_fidelity.append(path)
        return ReadinessReport(
            computational_ready=not missing,
            hardware_fidelity_ready=not missing and not low_fidelity,
            missing_required_measurements=tuple(sorted(missing)),
            non_fidelity_measurements=tuple(sorted(low_fidelity)),
        )
