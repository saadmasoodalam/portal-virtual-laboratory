from pydantic import BaseModel

from pvl.experiments.models import ExperimentConfig
from pvl.materials.library import load_builtin_material_library
from pvl.orchestrator.preflight import SolverRoute, preflight_experiment
from pvl.rig.fingerprint import rig_definition_fingerprint
from pvl.rig.measurements import CoordinateMeasurement, CountMeasurement, LengthMeasurement, MeasurementStatus
from pvl.rig.schema import RigV1Schema


def _fill(value):
    if isinstance(value, CoordinateMeasurement):
        value.value_m, value.status = 0.0, MeasurementStatus.ILLUSTRATIVE
    elif isinstance(value, LengthMeasurement):
        value.value_m, value.status = 0.1, MeasurementStatus.ILLUSTRATIVE
    elif isinstance(value, CountMeasurement):
        value.value, value.status = 10, MeasurementStatus.ILLUSTRATIVE
    elif isinstance(value, BaseModel):
        for name in value.__class__.model_fields:
            _fill(getattr(value, name))
    elif isinstance(value, list):
        for item in value:
            _fill(item)


def test_complete_exploratory_control_passes_preflight():
    rig = RigV1Schema()
    _fill(rig)
    materials = load_builtin_material_library()
    config = ExperimentConfig(
        experiment_id="ready-control",
        material_library_fingerprint=materials.fingerprint_sha256(),
        rig_definition_fingerprint=rig_definition_fingerprint(rig),
    )
    report = preflight_experiment(config, rig, materials)
    assert report.ready
    assert report.solver_route == SolverRoute.CONTROL
