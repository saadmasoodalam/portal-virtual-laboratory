from pvl.materials.library import load_builtin_material_library
from pvl.rig.material_check import check_material_references
from pvl.rig.schema import RigV1Schema


def test_default_material_references_exist_but_are_not_claimed_hardware_fidelity():
    report = check_material_references(RigV1Schema(), load_builtin_material_library())
    assert report.references_valid
    assert not report.hardware_fidelity_ready
    assert not report.missing_ids
    assert "mild_steel_linear_baseline" in report.lower_fidelity_ids
