from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from pvl.api.app import create_app
from pvl.experiments.models import ExperimentConfig
from pvl.experiments.package import persist_dc_experiment_package
from pvl.geometry.exploratory import architecture_example_rig_v1
from pvl.materials.library import load_builtin_material_library
from pvl.rig.fingerprint import rig_definition_fingerprint


def _setup(tmp_path: Path):
    rig = architecture_example_rig_v1()
    materials = load_builtin_material_library()
    config = ExperimentConfig(
        experiment_id="api-matrix-job-test",
        repetitions=1,
        randomization_seed=31,
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


def test_matrix_job_api_queues_without_running_solver_and_reports_status(tmp_path: Path):
    rig, materials, package = _setup(tmp_path)
    client = TestClient(create_app(materials=materials, results_root=tmp_path))
    response = client.post(
        "/api/v1/experiment/matrix/jobs",
        json={
            "experiment_id": "api-matrix-job-test",
            "package_id": package.manifest.package_id,
            "rig": rig.model_dump(mode="json"),
        },
    )
    assert response.status_code == 202
    queued = response.json()
    assert queued["status"] == "queued"
    assert queued["solver_execution_started"] is False
    assert queued["terminal"] is False
    assert queued["max_concurrent_solver_jobs"] == 1
    assert queued["biological_testing"] is False
    assert queued["hypothesis_analysis"] is False

    status = client.get(
        f"/api/v1/experiment/matrix/jobs/api-matrix-job-test/{queued['job_id']}"
    )
    assert status.status_code == 200
    assert status.json() == queued


def test_matrix_job_api_rejects_duplicate_and_unknown_status(tmp_path: Path):
    rig, materials, package = _setup(tmp_path)
    client = TestClient(create_app(materials=materials, results_root=tmp_path))
    request = {
        "experiment_id": "api-matrix-job-test",
        "package_id": package.manifest.package_id,
        "rig": rig.model_dump(mode="json"),
    }
    first = client.post("/api/v1/experiment/matrix/jobs", json=request)
    assert first.status_code == 202
    duplicate = client.post("/api/v1/experiment/matrix/jobs", json=request)
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "matrix_job_exists"

    missing = client.get(
        "/api/v1/experiment/matrix/jobs/api-matrix-job-test/matrix-job-does-not-exist"
    )
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "matrix_job_not_found"
