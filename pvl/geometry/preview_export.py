import json
from pathlib import Path

from pvl.geometry.preview import PreviewScene


def write_preview_scene(scene: PreviewScene, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(scene.model_dump(mode="json"), indent=2), encoding="utf-8")
    return path
