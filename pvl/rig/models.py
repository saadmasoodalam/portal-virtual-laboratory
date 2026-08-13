from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from pvl.rig.components import BoundaryGeometry, ChamberGeometry, CoilGeometry, Direction3D, FrameGeometry, SensorDefinition
from pvl.rig.measurements import CountMeasurement, LengthMeasurement


class RigReadinessReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    computational_ready: bool
    hardware_fidelity_ready: bool
    missing_required_measurements: tuple[str, ...]
    non_fidelity_measurements: tuple[str, ...]


def _measurements(value: Any, path: str = "") -> list[tuple[str, object]]:
    if isinstance(value, (LengthMeasurement, CountMeasurement)):
        return [(path, value)]
    result: list[tuple[str, object]] = []
    if isinstance(value, BaseModel):
        for name in value.__class__.model_fields:
            child_path = f"{path}.{name}" if path else name
            result.extend(_measurements(getattr(value, name), child_path))
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            result.extend(_measurements(child, f"{path}[{index}]"))
    return result


class RigV1Definition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rig_id: str = "portal_boundary_physics_rig_v1"
    ambient_material_id: str = "air_baseline"
    frame: FrameGeometry = Field(default_factory=FrameGeometry)
    copper_boundary: BoundaryGeometry = Field(default_factory=BoundaryGeometry)
    sample_chamber: ChamberGeometry = Field(default_factory=ChamberGeometry)
    coil_a: CoilGeometry = Field(default_factory=lambda: CoilGeometry(coil_id="A", axis=Direction3D(x=1.0, y=0.0, z=0.0)))
    coil_b: CoilGeometry = Field(default_factory=lambda: CoilGeometry(coil_id="B", axis=Direction3D(x=-1.0, y=0.0, z=0.0)))
    sensors: list[SensorDefinition] = Field(default_factory=list)

    def readiness_report(self) -> RigReadinessReport:
        missing: list[str] = []
        lower_fidelity: list[str] = []
        for path, item in _measurements(self):
            if not item.required_for_solver:
                continue
            if not item.has_value:
                missing.append(path)
            elif not item.is_hardware_fidelity:
                lower_fidelity.append(path)
        return RigReadinessReport(
            computational_ready=not missing,
            hardware_fidelity_ready=not missing and not lower_fidelity,
            missing_required_measurements=tuple(sorted(missing)),
            non_fidelity_measurements=tuple(sorted(lower_fidelity)),
        )
