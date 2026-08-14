from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import importlib

from fastapi.testclient import TestClient

from pvl.orchestrator.preflight import SolverRoute
from pvl.rig.schema import RigV1Schema


api_module = importlib.import_module("pvl.api.app")


def _request() -> dict:
    return {
        "experiment_id": "api-science-test",
        "package_id": "pkg-test",
        "run_id": "api-science-test-r01-s0001",
        "rig": RigV1Schema().model_dump(mode="json"),
        "single_run_confirmation": True,
    }


def test_scientific_run_endpoint_requires_explicit_confirmation(tmp_path: Path):
    client = TestClient(api_module.create_app(results_root=tmp_path))
    payload = _request()
    payload.pop("single_run_confirmation")
    assert client.post("/api/v1/experiment/execution/single/run", json=payload).status_code == 422
    payload["single_run_confirmation"] = False
    assert client.post("/api/v1/experiment/execution/single/run", json=payload).status_code == 422


def test_scientific_run_endpoint_reports_persisted_established_physics_scope(tmp_path: Path, monkeypatch):
    root = tmp_path / "api-science-test" / "executions" / "pkg-test" / "run" / "scientific" / "science-test"
    manifest = SimpleNamespace(
        job_id="science-test",
        job_fingerprint="a" * 64,
        package_id="pkg-test",
        run_id="api-science-test-r01-s0001",
        solver_route=SolverRoute.MAGNETOSTATIC,
        package_integrity_verified=True,
        preflight_ready=True,
        execution_allowed=True,
        solver_execution=True,
        single_run_only=True,
        batch_execution=False,
        biological_testing=False,
        hypothesis_analysis=False,
        physical_validation=False,
        geometry_fidelity="exploratory_constructive_contract",
        mesh_configuration_hash="b" * 64,
        metrics_file="metrics.json",
        summary_file="summary.csv",
    )

    def fake_execute(**kwargs):
        return SimpleNamespace(root=str(root), manifest=manifest)

    monkeypatch.setattr(api_module, "execute_and_persist_single_run", fake_execute)
    client = TestClient(api_module.create_app(results_root=tmp_path))
    response = client.post("/api/v1/experiment/execution/single/run", json=_request())
    assert response.status_code == 200
    payload = response.json()
    assert payload["solver_route"] == "magnetostatic"
    assert payload["solver_execution"] is True
    assert payload["hypothesis_analysis"] is False
    assert payload["physical_validation"] is False
    assert payload["biological_testing"] is False
    assert payload["single_run_only"] is True
    assert payload["batch_execution"] is False
    assert payload["metrics_file"] == "metrics.json"
    assert payload["summary_file"] == "summary.csv"
