from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from pvl.materials.models import MaterialDefinition


class MaterialLibraryPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    library_version: str = Field(min_length=1)
    materials: list[MaterialDefinition]


class MaterialLibrary:
    def __init__(self, payload: MaterialLibraryPayload):
        self.version = payload.library_version
        records: dict[str, MaterialDefinition] = {}
        for record in payload.materials:
            if record.material_id in records:
                raise ValueError(f"duplicate material_id: {record.material_id}")
            records[record.material_id] = record
        self._records = records

    @classmethod
    def from_json_file(cls, path: Path) -> "MaterialLibrary":
        payload = MaterialLibraryPayload.model_validate_json(path.read_text(encoding="utf-8"))
        return cls(payload)

    def get(self, material_id: str) -> MaterialDefinition | None:
        return self._records.get(material_id)

    def require(self, material_id: str) -> MaterialDefinition:
        record = self.get(material_id)
        if record is None:
            raise KeyError(f"unknown material_id: {material_id}")
        return record

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._records))

    def fingerprint_sha256(self) -> str:
        canonical = {
            "library_version": self.version,
            "materials": [
                self._records[key].model_dump(mode="json") for key in sorted(self._records)
            ],
        }
        encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def hardware_fidelity_warnings(self) -> tuple[str, ...]:
        warnings: list[str] = []
        for material_id in sorted(self._records):
            record = self._records[material_id]
            if not record.is_hardware_fidelity_data:
                warnings.append(
                    f"{material_id}: provenance={record.provenance.status}; replace with supplier/measured data for hardware-fidelity runs"
                )
            if record.solver_warning:
                warnings.append(f"{material_id}: {record.solver_warning}")
        return tuple(warnings)


def builtin_material_path() -> Path:
    return Path(__file__).with_name("data") / "builtin_v1.json"


def load_builtin_material_library() -> MaterialLibrary:
    return MaterialLibrary.from_json_file(builtin_material_path())
