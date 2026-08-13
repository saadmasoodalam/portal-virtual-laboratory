from __future__ import annotations

from hashlib import sha256
import json

from pvl.rig.schema import RigV1Schema


def rig_definition_fingerprint(rig: RigV1Schema) -> str:
    payload = json.dumps(
        rig.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(payload.encode("utf-8")).hexdigest()
