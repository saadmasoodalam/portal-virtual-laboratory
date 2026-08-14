from pathlib import Path

from pydantic import BaseModel

from pvl.experiments.models import ExperimentConfig
from pvl.experiments.package import persist_dc_experiment_package
from pvl.materials.library import load_builtin_material_library
from pvl.orchestrator.execution import evaluate_and_persist_single_run_gate
from pvl.orchestrator.execution_integrity import verify_execution_gate_checksums
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


def test_execution_gate_checksum_verifier_detects_tampering(tmp_path: Path):
    rig = RigV1Schema()
    _fill(rig)
    materials = load_builtin_material_library()
    config = ExperimentConfig(
        experiment_id="gate-integrity",
        repetitions=1,
        material_library_fingerprint=materials.fingerprint_sha256(),
        rig_definition_fingerprint=rig_definition_fingerprint(rig),
    )
    package = persist_dc_experiment_package(config, 1.0, tmp_path)
    run_id = package.manifest.run_ids[1]
    result = evaluate_and_persist_single_run_gate(
        package_root=Path(package.layout.root),
        run_id=run_id,
        rig=rig,
        materials=materials,
        results_root=tmp_path,
    )
    root = Path(result.root)
    assert verify_execution_gate_checksums(root)
    (root / "environment.json").write_text("{}", encoding="utf-8")
    assert not verify_execution_gate_checksums(root)
