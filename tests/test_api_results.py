from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from fastapi.testclient import TestClient

from pvl.api.app import create_app
from pvl.orchestrator.execution import _collect_checksums
from pvl.orchestrator.preflight import SolverRoute
from pvl.orchestrator.scientific_execution import ScientificRunManifest


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def _scientific_run(results_root: Path) -> Path:
    experiment_id = "results-test"
    package_id = "pkg-results"
    run_id = "results-test-r01-s0001"
    job_id = "science-results"
    root = (
        results_root
        / experiment_id
        / "executions"
        / package_id
        / run_id
        / "scientific"
        / job_id
    )
    root.mkdir(parents=True)
    (root / "raw").mkdir()
    manifest = ScientificRunManifest(
        job_id=job_id,
        job_fingerprint="a" * 64,
        package_id=package_id,
        package_fingerprint="b" * 64,
        plan_hash="c" * 64,
        run_id=run_id,
        planned_configuration_hash="d" * 64,
        physics_state_hash="e" * 64,
        rig_definition_fingerprint="f" * 64,
        material_library_fingerprint="1" * 64,
        constructive_topology_fingerprint="2" * 64,
        solver_route=SolverRoute.MAGNETOSTATIC,
        created_utc=datetime(2026, 8, 15, 1, 0, tzinfo=timezone.utc),
        solver_execution=True,
        geometry_fidelity="exploratory_constructive_contract",
        mesh_configuration_hash="3" * 64,
        solver_versions={"gmsh": "test", "getdp": "test"},
    )
    _write_json(root / "job_manifest.json", manifest.model_dump(mode="json"))
    _write_json(
        root / "metrics.json",
        {
            "solver_route": "magnetostatic",
            "solver_execution": True,
            "metrics": {"axis_center_b_y_t": 0.0125, "axis_peak_abs_b_t": 0.018},
        },
    )
    _write_json(root / "solver.json", {"solver_route": "magnetostatic", "solver_execution": True})
    _write_json(root / "experiment.json", {"run_id": run_id, "physics_state_hash": "e" * 64})
    _write_json(root / "geometry.json", {"geometry_fidelity": "exploratory_constructive_contract"})
    _write_json(root / "materials.json", {"library_fingerprint": "1" * 64})
    _write_json(root / "environment.json", {"python_version": "test"})
    (root / "summary.csv").write_text("metric,value,unit\naxis_center_b_y_t,0.0125,T\n", encoding="utf-8")
    _write_json(root / "checksums.json", _collect_checksums(root))
    return root


def test_results_api_lists_only_checksum_verified_runs_and_returns_metrics(tmp_path: Path):
    root = _scientific_run(tmp_path)
    client = TestClient(create_app(results_root=tmp_path))

    catalog_response = client.get("/api/v1/results/results-test")
    assert catalog_response.status_code == 200
    catalog = catalog_response.json()
    assert catalog["experiment_id"] == "results-test"
    assert len(catalog["runs"]) == 1
    summary = catalog["runs"][0]
    assert summary["checksum_verified"] is True
    assert summary["solver_execution"] is True
    assert summary["hypothesis_analysis"] is False
    assert summary["physical_validation"] is False

    detail_response = client.get(
        f"/api/v1/results/results-test/{summary['package_id']}/{summary['run_id']}/{summary['job_id']}"
    )
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["metrics"]["axis_center_b_y_t"] == 0.0125
    assert detail["metrics"]["axis_peak_abs_b_t"] == 0.018
    assert detail["solver_metadata"]["solver_route"] == "magnetostatic"

    (root / "metrics.json").write_text("{}", encoding="utf-8")
    filtered = client.get("/api/v1/results/results-test")
    assert filtered.status_code == 200
    assert filtered.json()["runs"] == []

    corrupt_detail = client.get(
        f"/api/v1/results/results-test/{summary['package_id']}/{summary['run_id']}/{summary['job_id']}"
    )
    assert corrupt_detail.status_code == 409
    assert corrupt_detail.json()["detail"]["code"] == "scientific_result_integrity_failed"


def test_results_api_returns_empty_catalog_for_experiment_without_runs(tmp_path: Path):
    client = TestClient(create_app(results_root=tmp_path))
    response = client.get("/api/v1/results/no-results-yet")
    assert response.status_code == 200
    assert response.json() == {"experiment_id": "no-results-yet", "runs": []}
