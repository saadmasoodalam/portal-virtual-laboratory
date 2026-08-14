from pathlib import Path

from fastapi.testclient import TestClient

from pvl.api.app import create_app
from pvl.experiments.models import ExperimentConfig
from pvl.geometry.exploratory import architecture_example_rig_v1
from pvl.materials.library import load_builtin_material_library
from pvl.rig.fingerprint import rig_definition_fingerprint
from pvl.sweeps.package import verify_dc_sweep_plan


def _request():
    rig = architecture_example_rig_v1()
    materials = load_builtin_material_library()
    experiment = ExperimentConfig(
        experiment_id="api-sweep-base",
        repetitions=1,
        material_library_fingerprint=materials.fingerprint_sha256(),
        rig_definition_fingerprint=rig_definition_fingerprint(rig),
    )
    return materials, {
        "definition": {
            "sweep_id": "api-sweep",
            "coil_a_current_a": {"start": -1.0, "stop": 1.0, "step": 1.0},
            "coil_b_current_a": {"start": -1.0, "stop": 1.0, "step": 1.0},
            "media": ["air", "distilled_water", "saline_0p9"],
            "copper_boundary_states": ["open", "closed"],
            "maximum_points": 1000,
        },
        "rig": rig.model_dump(mode="json"),
        "experiment": experiment.model_dump(mode="json"),
        "persist": False,
    }


def test_sweep_api_plans_compact_deterministic_identity_without_solver_execution(tmp_path: Path):
    materials, request = _request()
    client = TestClient(create_app(materials=materials, results_root=tmp_path))
    response = client.post("/api/v1/sweeps/dc/plan", json=request)
    assert response.status_code == 200
    payload = response.json()
    assert payload["point_count"] == 3 * 3 * 3 * 2 == 54
    assert payload["coil_a_value_count"] == 3
    assert payload["coil_b_value_count"] == 3
    assert payload["medium_count"] == 3
    assert payload["copper_state_count"] == 2
    assert payload["solver_execution"] is False
    assert payload["hypothesis_analysis"] is False
    assert payload["persisted"] is False
    assert payload["relative_path"] is None
    assert len(payload["point_ids"]) == 54
    assert len(set(payload["point_hashes"])) == 54


def test_sweep_api_can_persist_immutable_plan_and_reject_duplicate(tmp_path: Path):
    materials, request = _request()
    request["persist"] = True
    client = TestClient(create_app(materials=materials, results_root=tmp_path))
    first = client.post("/api/v1/sweeps/dc/plan", json=request)
    assert first.status_code == 200
    payload = first.json()
    assert payload["persisted"] is True
    root = tmp_path / payload["relative_path"]
    assert verify_dc_sweep_plan(root)

    duplicate = client.post("/api/v1/sweeps/dc/plan", json=request)
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "dc_sweep_exists"


def test_sweep_api_rejects_cardinality_over_limit(tmp_path: Path):
    materials, request = _request()
    request["definition"]["maximum_points"] = 20
    client = TestClient(create_app(materials=materials, results_root=tmp_path))
    response = client.post("/api/v1/sweeps/dc/plan", json=request)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "dc_sweep_invalid"
