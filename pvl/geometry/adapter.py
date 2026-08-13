from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from pvl.geometry.preview import PreviewScene, build_preview_scene
from pvl.geometry.rig_compile import compile_rig_geometry
from pvl.materials.library import MaterialLibrary
from pvl.rig.material_check import check_material_references
from pvl.rig.schema import RigV1Schema


class GeometryAdapterMode(StrEnum):
    PREVIEW = "preview"
    HARDWARE_FIDELITY = "hardware_fidelity"


class GeometryAdapterStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    mode: GeometryAdapterMode
    ready: bool
    reasons: tuple[str, ...]


def adapter_status(
    rig: RigV1Schema,
    materials: MaterialLibrary,
    mode: GeometryAdapterMode,
) -> GeometryAdapterStatus:
    readiness = rig.readiness_report()
    material_report = check_material_references(rig, materials)
    reasons: list[str] = []

    if not readiness.computational_ready:
        reasons.append("required_geometry_measurements_missing")
    if not material_report.references_valid:
        reasons.append("material_reference_missing")

    if mode == GeometryAdapterMode.HARDWARE_FIDELITY:
        if not readiness.hardware_fidelity_ready:
            reasons.append("geometry_not_hardware_fidelity")
        if not material_report.hardware_fidelity_ready:
            reasons.append("materials_not_hardware_fidelity")
        reasons.append("constructive_hardware_adapter_not_implemented")

    return GeometryAdapterStatus(mode=mode, ready=not reasons, reasons=tuple(reasons))


def build_preview_from_rig(rig: RigV1Schema, materials: MaterialLibrary) -> PreviewScene:
    status = adapter_status(rig, materials, GeometryAdapterMode.PREVIEW)
    if not status.ready:
        raise ValueError("preview geometry is not ready: " + ", ".join(status.reasons))
    return build_preview_scene(compile_rig_geometry(rig))


def require_hardware_adapter(rig: RigV1Schema, materials: MaterialLibrary) -> None:
    status = adapter_status(rig, materials, GeometryAdapterMode.HARDWARE_FIDELITY)
    if not status.ready:
        raise NotImplementedError("hardware geometry adapter unavailable: " + ", ".join(status.reasons))
