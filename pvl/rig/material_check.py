from pydantic import BaseModel, ConfigDict

from pvl.materials.library import MaterialLibrary
from pvl.rig.schema import RigV1Schema


class MaterialReferenceReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    references_valid: bool
    hardware_fidelity_ready: bool
    missing_ids: tuple[str, ...]
    lower_fidelity_ids: tuple[str, ...]


def material_ids(rig: RigV1Schema) -> tuple[str, ...]:
    return tuple(sorted({
        rig.ambient_material_id,
        rig.frame.material_id,
        rig.copper_boundary.material_id,
        rig.sample_chamber.wall_material_id,
        rig.sample_chamber.medium_material_id,
        rig.coil_a.conductor_material_id,
        rig.coil_b.conductor_material_id,
    }))


def check_material_references(rig: RigV1Schema, library: MaterialLibrary) -> MaterialReferenceReport:
    missing: list[str] = []
    lower: list[str] = []
    for material_id in material_ids(rig):
        record = library.get(material_id)
        if record is None:
            missing.append(material_id)
        elif not record.is_hardware_fidelity_data:
            lower.append(material_id)
    return MaterialReferenceReport(
        references_valid=not missing,
        hardware_fidelity_ready=not missing and not lower,
        missing_ids=tuple(missing),
        lower_fidelity_ids=tuple(lower),
    )
