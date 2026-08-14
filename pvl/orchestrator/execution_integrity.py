from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_execution_gate_checksums(root: Path) -> bool:
    """Verify the exact persisted file set for one PVL-2N execution-gate overlay."""
    checksum_path = root / "checksums.json"
    if not root.is_dir() or not checksum_path.is_file():
        return False
    try:
        payload = json.loads(checksum_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict) or not all(
        isinstance(path, str) and isinstance(digest, str) for path, digest in payload.items()
    ):
        return False
    current = {
        str(path.relative_to(root)): _file_sha256(path)
        for path in sorted(item for item in root.rglob("*") if item.is_file() and item.name != "checksums.json")
    }
    return current == payload
