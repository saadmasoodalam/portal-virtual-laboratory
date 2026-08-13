from pvl.rig.io import load_rig, write_rig
from pvl.rig.schema import RigV1Schema


def test_rig_json_roundtrip(tmp_path):
    path = write_rig(RigV1Schema(), tmp_path / "rig.json")
    assert load_rig(path) == RigV1Schema()
