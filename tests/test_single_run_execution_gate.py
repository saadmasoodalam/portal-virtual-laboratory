from datetime import datetime, timezone
import json
from pathlib import Path

from pydantic import BaseModel
import pytest

from pvl.experiments.models import ExperimentConfig
from pvl.experiments.package import persist_dc_experiment_package, verify_experiment_package_checksums
from pvl.materials.library import load_builtin_material_library
from pvl.orchestrator.execution import (
    PackageIntegrityError,
    PlannedRunNotFoundError,
    evaluate_and_persist_single_run_gate,
)
from pvl.orchestrator.preflight import SolverRoute
from pvl.rig.fingerprint import rig_definition_fingerprint
from pvl.rig.measurements import CoordinateMeasurement, CountMeasurement, LengthMeasurement, MeasurementStatus
from pvl.rig.schema import RigV1Schema


def _fill_illustrative(value):
    if isinstance(value, CoordinateMeasurement):
        value.value_m, value.status = 0.0, MeasurementStatus.ILLUSTRATIVE
    elif isinstance(value, LengthMeasurement):
        value.value_m, value.status = 0.1, MeasurementStatus.ILLUSTRATIVE
    elif isinstance(value, CountMeasurement):
        value.value, value.status = 10, MeasurementStatus.ILLUSTRATIVE
    elif isinstance(value, BaseModel):
        for name in value.__class__.model_fields:
            _fill_illustrative(getattr(value, name))
    elif isinstance(value, list):
        for item in value:
            _fill_illustrative(item)


def _rig_and_config() -> tuple[RigV1Schema, ExperimentConfig]:
    rig = RigV1Schema()
    _fill_illustrative(rig)
    materials = load_builtin_material_library()
    config = ExperimentConfig(
        experiment_id="gate-test",
        repetitions=1,
        randomization_seed=19,
        material_library_fingerprint=materials.fingerprint_sha256(),
        rig_definition_fingerprint=rig_definition_fingerprint(rig),
    )
    return rig, config


def _persist(tmp_path: Path):
    rig, config = _rig_and_config()
    package = persist_dc_experiment_package(
        config,
        1.0,
        tmp_path,
        created_utc=datetime(2026, 8, 14, 0, 0, tzinfo=timezone.utc),
    )
    matrix = json.loads(Path(package.layout.run_matrix_json).read_text(encoding="utf-8"))
    return rig, package, matrix


def test_active_dc_run_is_preflight_ready_but_blocked_without_constructive_solver_geometry(tmp_path: Path):
    rig, package, matrix = _persist(tmp_path)
    materials = load_builtin_material_library()
    active = next(row for row in matrix if row["state_id"] != "off_off")
    package_root = Path(package.layout.root)

    result = evaluate_and_persist_single_run_gate(
        package_root=package_root,
        run_id=active["run_id"],
        rig=rig,
        materials=materials,
        results_root=tmp_path,
        created_utc=datetime(2026, 8, 14, 1, 0, tzinfo=timezone.utc),
    )

    manifest = result.manifest
    assert manifest.solver_route == SolverRoute.MAGNETOSTATIC
    assert manifest.package_integrity_verified is True
    assert manifest.preflight_ready is True
    assert manifest.execution_allowed is False
    assert manifest.solver_execution is False
    assert manifest.single_run_only is True
    assert manifest.batch_execution is False
    assert manifest.biological_testing is False
    assert [issue.code for issue in manifest.issues] == ["constructive_solver_geometry_unavailable"]
    assert (Path(result.root) / "job_manifest.json").is_file()
    assert (Path(result.root) / "environment.json").is_file()
    assert (Path(result.root) / "checksums.json").is_file()
    assert (Path(result.root) / "raw").is_dir()
    assert not (Path(result.root) / "mesh.msh").exists()
    assert not (Path(result.root) / "solver_input.pro").exists()
    assert not (Path(result.root) / "fields.vtu").exists()
    assert verify_experiment_package_checksums(package_root)


def test_off_off_control_can_pass_gate_without_claiming_solver_execution(tmp_path: Path):
    rig, package, matrix = _persist(tmp_path)
    control = next(row for row in matrix if row["state_id"] == "off_off")
    result = evaluate_and_persist_single_run_gate(
        package_root=Path(package.layout.root),
        run_id=control["run_id"],
        rig=rig,
        materials=load_builtin_material_library(),
        results_root=tmp_path,
    )
    assert result.manifest.solver_route == SolverRoute.CONTROL
    assert result.manifest.preflight_ready is True
    assert result.manifest.execution_allowed is True
    assert result.manifest.solver_execution is False
    assert result.manifest.issues == ()


def test_unknown_run_is_rejected_before_job_record_is_created(tmp_path: Path):
    rig, package, _ = _persist(tmp_path)
    with pytest.raises(PlannedRunNotFoundError):
        evaluate_and_persist_single_run_gate(
            package_root=Path(package.layout.root),
            run_id="gate-test-r99-s9999",
            rig=rig,
            materials=load_builtin_material_library(),
            results_root=tmp_path,
        )
    assert not (tmp_path / "gate-test" / "executions").exists()


def test_package_tampering_blocks_gate_and_creates_no_execution_overlay(tmp_path: Path):
    rig, package, matrix = _persist(tmp_path)
    active = next(row for row in matrix if row["state_id"] != "off_off")
    Path(package.layout.experiment_json).write_text("{}", encoding="utf-8")
    with pytest.raises(PackageIntegrityError):
        evaluate_and_persist_single_run_gate(
            package_root=Path(package.layout.root),
            run_id=active["run_id"],
            rig=rig,
            materials=load_builtin_material_library(),
            results_root=tmp_path,
        )
    assert not (tmp_path / "gate-test" / "executions").exists()


def test_rig_fingerprint_mismatch_is_recorded_as_blocking_preflight_issue(tmp_path: Path):
    rig, package, matrix = _persist(tmp_path)
    active = next(row for row in matrix if row["state_id"] != "off_off")
    rig.frame.outer_width.value_m = 0.2
    result = evaluate_and_persist_single_run_gate(
        package_root=Path(package.layout.root),
        run_id=active["run_id"],
        rig=rig,
        materials=load_builtin_material_library(),
        results_root=tmp_path,
    )
    codes = {issue.code for issue in result.manifest.issues}
    assert "rig_fingerprint_mismatch" in codes
    assert "constructive_solver_geometry_unavailable" in codes
    assert result.manifest.preflight_ready is False
    assert result.manifest.execution_allowed is False


def test_same_gate_identity_is_deterministic_and_never_overwritten(tmp_path: Path):
    rig, package, matrix = _persist(tmp_path)
    active = next(row for row in matrix if row["state_id"] != "off_off")
    kwargs = dict(
        package_root=Path(package.layout.root),
        run_id=active["run_id"],
        rig=rig,
        materials=load_builtin_material_library(),
        results_root=tmp_path,
    )
    first = evaluate_and_persist_single_run_gate(**kwargs)
    with pytest.raises(FileExistsError):
        evaluate_and_persist_single_run_gate(**kwargs)
    assert Path(first.root).is_dir()
