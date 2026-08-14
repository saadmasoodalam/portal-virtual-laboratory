from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from pvl.experiments.models import ExperimentConfig
from pvl.experiments.package import persist_dc_experiment_package
from pvl.geometry.exploratory import architecture_example_rig_v1
from pvl.materials.library import load_builtin_material_library
from pvl.orchestrator.execution import PackageIntegrityError
from pvl.orchestrator.jobs import (
    MatrixJobError,
    enqueue_dc_matrix_job,
    load_matrix_job_status,
    run_queued_dc_matrix_job,
)
from pvl.orchestrator.scientific_execution import exploratory_complete_rig_dc_mesh_profile
from pvl.rig.fingerprint import rig_definition_fingerprint


def _fixture(tmp_path: Path):
    rig = architecture_example_rig_v1()
    materials = load_builtin_material_library()
    config = ExperimentConfig(
        experiment_id="matrix-job-test",
        repetitions=1,
        randomization_seed=29,
        material_library_fingerprint=materials.fingerprint_sha256(),
        rig_definition_fingerprint=rig_definition_fingerprint(rig),
    )
    package = persist_dc_experiment_package(
        config,
        1.0,
        tmp_path,
        created_utc=datetime(2026, 8, 15, 0, 0, tzinfo=timezone.utc),
    )
    return rig, materials, package


def test_matrix_job_enqueue_is_durable_immutable_and_initially_solver_free(tmp_path: Path):
    rig, materials, package = _fixture(tmp_path)
    status = enqueue_dc_matrix_job(
        package_root=Path(package.layout.root),
        rig=rig,
        materials=materials,
        results_root=tmp_path,
        mesh_config=exploratory_complete_rig_dc_mesh_profile(),
        created_utc=datetime(2026, 8, 15, 1, 0, tzinfo=timezone.utc),
    )
    assert status.latest_event.status == "queued"
    assert status.event_count == 1
    assert status.request.max_concurrent_solver_jobs == 1
    assert status.request.biological_testing is False
    assert status.request.hypothesis_analysis is False
    root = tmp_path / "matrix-job-test" / "jobs" / status.request.job_id
    assert (root / "request.json").is_file()
    assert (root / "request.sha256").is_file()
    assert (root / "events" / "000000-queued.json").is_file()
    assert not (root / "claim.json").exists()

    loaded = load_matrix_job_status(
        results_root=tmp_path,
        experiment_id="matrix-job-test",
        job_id=status.request.job_id,
    )
    assert loaded == status
    with pytest.raises(FileExistsError, match="already exists"):
        enqueue_dc_matrix_job(
            package_root=Path(package.layout.root),
            rig=rig,
            materials=materials,
            results_root=tmp_path,
            mesh_config=exploratory_complete_rig_dc_mesh_profile(),
        )


def test_matrix_worker_claims_once_and_records_terminal_success(tmp_path: Path):
    rig, materials, package = _fixture(tmp_path)
    queued = enqueue_dc_matrix_job(
        package_root=Path(package.layout.root),
        rig=rig,
        materials=materials,
        results_root=tmp_path,
        mesh_config=exploratory_complete_rig_dc_mesh_profile(),
    )
    matrix_root = tmp_path / "matrix-job-test" / "matrix_executions" / "pkg" / "matrix-fake"
    matrix_root.mkdir(parents=True)
    calls = 0

    def fake_matrix_executor(**kwargs):
        nonlocal calls
        calls += 1
        return SimpleNamespace(root=str(matrix_root))

    done = run_queued_dc_matrix_job(
        results_root=tmp_path,
        experiment_id="matrix-job-test",
        job_id=queued.request.job_id,
        materials=materials,
        matrix_executor=fake_matrix_executor,
    )
    assert calls == 1
    assert done.latest_event.status == "succeeded"
    assert done.event_count == 3
    assert done.latest_event.matrix_result_path.endswith("matrix-fake")
    job_root = tmp_path / "matrix-job-test" / "jobs" / queued.request.job_id
    assert (job_root / "claim.json").is_file()
    assert (job_root / "events" / "000001-running.json").is_file()
    assert (job_root / "events" / "000002-succeeded.json").is_file()
    with pytest.raises(MatrixJobError, match="not queued"):
        run_queued_dc_matrix_job(
            results_root=tmp_path,
            experiment_id="matrix-job-test",
            job_id=queued.request.job_id,
            materials=materials,
            matrix_executor=fake_matrix_executor,
        )


def test_matrix_worker_records_failure_as_terminal_event(tmp_path: Path):
    rig, materials, package = _fixture(tmp_path)
    queued = enqueue_dc_matrix_job(
        package_root=Path(package.layout.root),
        rig=rig,
        materials=materials,
        results_root=tmp_path,
        mesh_config=exploratory_complete_rig_dc_mesh_profile(),
    )

    def failing_matrix_executor(**kwargs):
        raise RuntimeError("synthetic worker failure")

    failed = run_queued_dc_matrix_job(
        results_root=tmp_path,
        experiment_id="matrix-job-test",
        job_id=queued.request.job_id,
        materials=materials,
        matrix_executor=failing_matrix_executor,
    )
    assert failed.latest_event.status == "failed"
    assert failed.latest_event.error_type == "RuntimeError"
    assert "synthetic worker failure" in failed.latest_event.message
    assert failed.event_count == 3


def test_matrix_job_request_tampering_is_detected_before_status_read(tmp_path: Path):
    rig, materials, package = _fixture(tmp_path)
    queued = enqueue_dc_matrix_job(
        package_root=Path(package.layout.root),
        rig=rig,
        materials=materials,
        results_root=tmp_path,
        mesh_config=exploratory_complete_rig_dc_mesh_profile(),
    )
    request_path = (
        tmp_path / "matrix-job-test" / "jobs" / queued.request.job_id / "request.json"
    )
    request_path.write_text("{}", encoding="utf-8")
    with pytest.raises(PackageIntegrityError, match="checksum"):
        load_matrix_job_status(
            results_root=tmp_path,
            experiment_id="matrix-job-test",
            job_id=queued.request.job_id,
        )
