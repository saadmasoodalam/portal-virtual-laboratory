from pvl.experiments.models import ExperimentConfig
from pvl.materials.library import load_builtin_material_library
from pvl.orchestrator.preflight import preflight_experiment
from pvl.rig.fingerprint import rig_definition_fingerprint
from pvl.rig.schema import RigV1Schema


def test_default_rig_reports_not_ready():
    rig = RigV1Schema()
    materials = load_builtin_material_library()
    config = ExperimentConfig(
        experiment_id="check",
        material_library_fingerprint=materials.fingerprint_sha256(),
        rig_definition_fingerprint=rig_definition_fingerprint(rig),
    )
    report = preflight_experiment(config, rig, materials)
    assert report.ready is False
