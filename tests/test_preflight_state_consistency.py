from pvl.experiments.models import BoundaryCircuitState, ExperimentConfig, SampleMedium
from pvl.geometry.exploratory import architecture_example_rig_v1
from pvl.materials.library import load_builtin_material_library
from pvl.orchestrator.preflight import preflight_experiment
from pvl.rig.fingerprint import rig_definition_fingerprint


def _config() -> tuple[object, object, ExperimentConfig]:
    rig = architecture_example_rig_v1()
    materials = load_builtin_material_library()
    config = ExperimentConfig(
        experiment_id="state-consistency-test",
        repetitions=1,
        material_library_fingerprint=materials.fingerprint_sha256(),
        rig_definition_fingerprint=rig_definition_fingerprint(rig),
    )
    return rig, materials, config


def test_matching_medium_and_copper_state_pass_state_geometry_consistency():
    rig, materials, config = _config()
    report = preflight_experiment(config, rig, materials)
    codes = {issue.code for issue in report.issues}
    assert "sample_medium_geometry_mismatch" not in codes
    assert "copper_boundary_geometry_mismatch" not in codes


def test_experiment_medium_cannot_disagree_with_material_compiled_into_rig():
    rig, materials, config = _config()
    mismatched = config.model_copy(update={"medium": SampleMedium.SALINE_0P9})
    report = preflight_experiment(mismatched, rig, materials)
    assert not report.ready
    assert "sample_medium_geometry_mismatch" in {issue.code for issue in report.issues}


def test_experiment_open_closed_state_cannot_disagree_with_rig_topology():
    rig, materials, config = _config()
    mismatched = config.model_copy(update={"copper_boundary_state": BoundaryCircuitState.CLOSED})
    report = preflight_experiment(mismatched, rig, materials)
    assert not report.ready
    assert "copper_boundary_geometry_mismatch" in {issue.code for issue in report.issues}
