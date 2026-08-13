from pydantic import BaseModel, ConfigDict

from pvl.geometry.rig_manifest import RigGeometryManifest
from pvl.rig.fingerprint import rig_definition_fingerprint
from pvl.rig.schema import RigV1Schema


class GeometryCompilationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    rig_fingerprint: str
    geometry_fingerprint: str


def compilation_record(rig: RigV1Schema, geometry: RigGeometryManifest) -> GeometryCompilationRecord:
    return GeometryCompilationRecord(
        rig_fingerprint=rig_definition_fingerprint(rig),
        geometry_fingerprint=geometry.fingerprint_sha256(),
    )
