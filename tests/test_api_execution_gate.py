from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import BaseModel

from pvl.api.app import create_app
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


def _persist_package(client: TestClient, rig: RigV1Schema) -> tuple[dict, dict]:
    experiment = client.post(
        "/api/v1/experiment/template",
        json=rig.model_dump(mode="json"),
    ).json()
    experiment["experiment_id"] = "api-gate-test"
    experiment["repetitions"] = 1
    plan = client.post(
        "/api/v1/experiment/plan/dc",
        json={"experiment": experiment, "current_a": 1.0},
    ).json()
    package = client.post(
        "/api/v1/experiment/plan/dc/persist",
        json={"experiment": experiment, "current_a": 1.0},
    ).json()
    return package, plan


def test_api_authorizes_active_magnetostatic_run_without_executing_solver_in_gate(tmp_path: Path):
    client = TestClient(create_app(results_root=tmp_path))
    rig = RigV1Schema()
    _fill_illustrative(rig)
    package, plan = _persist_package(client, rig)
    active = next(run for run in plan["runs"] if run["state_id"] != "off_off")

    response = client.post(
        "/api/v1/experiment/execution/single/gate",
        json={
            "experiment_id": "api-gate-test",
            "package_id": package["package_id"],
            "run_id": active["run_id"],
            "rig": rig.model_dump(mode="json"),
            "single_run_confirmation": True,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["solver_route"] == "magnetostatic"
    assert payload["package_integrity_verified"] is True
    assert payload["preflight_ready"] is True
    assert payload["execution_allowed"] is True
    assert payload["solver_execution"] is False
    assert payload["single_run_only"] is True
    assert payload["batch_execution"] is False
    assert payload["biological_testing"] is False
    assert payload["issues"] == []

    root = tmp_path / payload["relative_execution_path"]
    assert (root / "job_manifest.json").is_file()
    assert (root / "environment.json").is_file()
    assert (root / "checksums.json").is_file()
    assert (root / "raw").is_dir()
    assert not (root / "mesh.msh").exists()
    assert not (root / "solver_input.pro").exists()


def test_api_requires_explicit_single_run_confirmation(tmp_path: Path):
    client = TestClient(create_app(results_root=tmp_path))
    rig = RigV1Schema()
    _fill_illustrative(rig)
    package, plan = _persist_package(client, rig)
    active = next(run for run in plan["runs"] if run["state_id"] != "off_off")
    base = {
        "experiment_id": "api-gate-test",
        "package_id": package["package_id"],
        "run_id": active["run_id"],
        "rig": rig.model_dump(mode="json"),
    }
    assert client.post("/api/v1/experiment/execution/single/gate", json=base).status_code == 422
    assert client.post(
        "/api/v1/experiment/execution/single/gate",
        json={**base, "single_run_confirmation": False},
    ).status_code == 422


def test_api_unknown_run_returns_404_without_execution_record(tmp_path: Path):
    client = TestClient(create_app(results_root=tmp_path))
    rig = RigV1Schema()
    _fill_illustrative(rig)
    package, _ = _persist_package(client, rig)
    response = client.post(
        "/api/v1/experiment/execution/single/gate",
        json={
            "experiment_id": "api-gate-test",
            "package_id": package["package_id"],
            "run_id": "api-gate-test-r99-s9999",
            "rig": rig.model_dump(mode="json"),
            "single_run_confirmation": True,
        },
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "planned_run_not_found"
    assert not (tmp_path / "api-gate-test" / "executions").exists()
