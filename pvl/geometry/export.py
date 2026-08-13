import json
from pathlib import Path

from pvl.geometry.rig_compile import compile_rig_geometry
from pvl.rig.schema import RigV1Schema


def write_manifest(rig: RigV1Schema, path: Path) -> Path:
    data = compile_rig_geometry(rig)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data.model_dump(mode="json"), indent=2), encoding="utf-8")
    return path
