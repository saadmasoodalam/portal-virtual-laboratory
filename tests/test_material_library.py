from pvl.materials.library import load_builtin_material_library
from pvl.materials.models import MaterialModelKind


def test_builtin_material_ids_are_stable_and_unique():
    library = load_builtin_material_library()
    assert library.ids() == (
        "air_baseline",
        "borosilicate_glass_baseline",
        "copper_baseline",
        "distilled_water_baseline",
        "mild_steel_linear_baseline",
        "saline_0p9_baseline",
    )


def test_material_library_fingerprint_is_deterministic():
    first = load_builtin_material_library()
    second = load_builtin_material_library()
    assert first.fingerprint_sha256() == second.fingerprint_sha256()
    assert len(first.fingerprint_sha256()) == 64


def test_steel_baseline_is_explicitly_a_linear_placeholder():
    steel = load_builtin_material_library().require("mild_steel_linear_baseline")
    assert steel.model_kind == MaterialModelKind.LINEAR_PLACEHOLDER
    assert steel.solver_warning
    assert not steel.is_hardware_fidelity_data


def test_salinity_record_is_labeled_as_comparison_baseline():
    saline = load_builtin_material_library().require("saline_0p9_baseline")
    assert "comparison" in saline.display_name.lower()
    assert not saline.is_hardware_fidelity_data
