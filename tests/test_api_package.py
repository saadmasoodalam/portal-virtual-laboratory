from pathlib import Path

from fastapi.testclient import TestClient

from pvl.api.app import create_app
from pvl.rig.schema import RigV1Schema


def test_persist_dc_package_writes_planned_package_without_solver_outputs(tmp_path: Path):
    client = TestClient(create_app(results_root=tmp_path))
    rig = RigV1Schema()
    experiment = client.post(
        "/api/v1/experiment/template",
        json=rig.model_dump(mode="json"),
    ).json()
    experiment["repetitions"] = 2
    experiment["randomization_seed"] = 17

    response = client.post(
        "/api/v1/experiment/plan/dc/persist",
        json={"experiment": experiment, "current_a": 1.25},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["solver_execution"] is False
    assert payload["run_count"] == 18
    assert len(payload["plan_hash"]) == 64
    assert len(payload["package_fingerprint"]) == 64
    assert payload["checksummed_files"] >= 21

    package_root = tmp_path / payload["relative_path"]
    assert (package_root / "experiment.json").is_file()
    assert (package_root / "run_matrix.json").is_file()
    assert (package_root / "package_manifest.json").is_file()
    assert (package_root / "checksums.json").is_file()
    assert len(list((package_root / "runs").glob("*/manifest.json"))) == 18
    assert not list(package_root.glob("runs/*/mesh.msh"))
    assert not list(package_root.glob("runs/*/solver_input.pro"))
    assert not list(package_root.glob("runs/*/fields.vtu"))


def test_persist_dc_package_refuses_to_overwrite_existing_package(tmp_path: Path):
    client = TestClient(create_app(results_root=tmp_path))
    experiment = client.post(
        "/api/v1/experiment/template",
        json=RigV1Schema().model_dump(mode="json"),
    ).json()
    request = {"experiment": experiment, "current_a": 1.0}
    assert client.post("/api/v1/experiment/plan/dc/persist", json=request).status_code == 200
    second = client.post("/api/v1/experiment/plan/dc/persist", json=request)
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "experiment_package_exists"
