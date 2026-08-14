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


def _run(
    root: Path,
    *,
    package: str,
    run_id: str,
    job_id: str,
    value: float,
    mesh_hash: str = "3" * 64,
) -> None:
    target = root / "compare-api" / "executions" / package / run_id / "scientific" / job_id
    target.mkdir(parents=True)
    (target / "raw").mkdir()
    manifest = ScientificRunManifest(
        job_id=job_id,
        job_fingerprint=(job_id[-1] * 64)[:64],
        package_id=package,
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
        mesh_configuration_hash=mesh_hash,
    )
    _write_json(target / "job_manifest.json", manifest.model_dump(mode="json"))
    _write_json(target / "metrics.json", {"metrics": {"signal": value, "temperature_k": 293.15}})
    _write_json(target / "solver.json", {"solver_route": "magnetostatic", "solver_execution": True})
    _write_json(
        target / "experiment.json",
        {"run_id": run_id, "configuration_hash": "d" * 64, "physics_state_hash": "e" * 64},
    )
    _write_json(target / "geometry.json", {"geometry_fidelity": "exploratory_constructive_contract"})
    _write_json(target / "materials.json", {"library_fingerprint": "1" * 64})
    _write_json(target / "environment.json", {"python_version": "test"})
    (target / "summary.csv").write_text("metric,value,unit\nsignal,1,1\n", encoding="utf-8")
    _write_json(target / "checksums.json", _collect_checksums(target))


def test_comparison_api_reads_only_checksum_verified_server_results(tmp_path: Path):
    references = []
    for state, x, base in (("state-a", 0.0, 1.0), ("state-a", 1.0, 2.0), ("state-a", 2.0, 3.0)):
        for repetition in range(3):
            run_id = f"run-{int(x)}-{repetition}"
            job_id = f"science-{int(x)}{repetition}a"
            _run(tmp_path, package="pkg", run_id=run_id, job_id=job_id, value=base + repetition * 0.0001)
            references.append(
                {
                    "package_id": "pkg",
                    "run_id": run_id,
                    "job_id": job_id,
                    "state_id": state,
                    "repetition_index": repetition,
                    "parameter_value": x,
                }
            )

    client = TestClient(create_app(results_root=tmp_path))
    response = client.post(
        "/api/v1/comparisons/physics",
        json={
            "comparison_id": "api-comparison",
            "experiment_id": "compare-api",
            "parameter_name": "current_a",
            "metric_name": "signal",
            "runs": references,
            "minimum_repetitions": 3,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["repeatability_gate_passed"] is True
    assert payload["mesh_identity_gate_passed"] is True
    assert payload["all_samples_checksum_verified"] is True
    assert payload["portal_interpretation_allowed"] is False
    assert payload["unexplained_residual_claim_allowed"] is False


def test_comparison_api_rejects_tampered_result_before_analysis(tmp_path: Path):
    _run(tmp_path, package="pkg", run_id="run-0", job_id="science-0a", value=1.0)
    target = tmp_path / "compare-api" / "executions" / "pkg" / "run-0" / "scientific" / "science-0a"
    (target / "metrics.json").write_text("{}", encoding="utf-8")

    client = TestClient(create_app(results_root=tmp_path))
    response = client.post(
        "/api/v1/comparisons/physics",
        json={
            "comparison_id": "tampered",
            "experiment_id": "compare-api",
            "parameter_name": "current_a",
            "metric_name": "signal",
            "runs": [
                {
                    "package_id": "pkg",
                    "run_id": "run-0",
                    "job_id": "science-0a",
                    "state_id": "state-a",
                    "repetition_index": 0,
                    "parameter_value": 0.0,
                }
            ],
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "scientific_result_integrity_failed"
