import json
from pathlib import Path

from pvl.rig.schema import RigV1Schema


def load_rig(path: Path) -> RigV1Schema:
    return RigV1Schema.model_validate_json(path.read_text(encoding="utf-8"))


def write_rig(rig: RigV1Schema, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rig.model_dump(mode="json"), indent=2), encoding="utf-8")
    return path
