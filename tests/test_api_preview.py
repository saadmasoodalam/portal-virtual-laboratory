from fastapi.testclient import TestClient
from pydantic import BaseModel

from pvl.api.app import create_app
from pvl.rig.measurements import CoordinateMeasurement, CountMeasurement, LengthMeasurement, MeasurementStatus
from pvl.rig.schema import RigV1Schema


def complete_rig() -> RigV1Schema:
    rig = RigV1Schema()

    def fill(value):
        if isinstance(value, CoordinateMeasurement):
            value.value_m = 0.0
            value.status = MeasurementStatus.ILLUSTRATIVE
        elif isinstance(value, LengthMeasurement):
            value.value_m = 0.1
            value.status = MeasurementStatus.ILLUSTRATIVE
        elif isinstance(value, CountMeasurement):
            value.value = 10
            value.status = MeasurementStatus.ILLUSTRATIVE
        elif isinstance(value, BaseModel):
            for name in value.__class__.model_fields:
                fill(getattr(value, name))
        elif isinstance(value, list):
            for item in value:
                fill(item)

    fill(rig)
    rig.sample_chamber.wall_thickness.value_m = 0.01
    rig.copper_boundary.strip_width.value_m = 0.01
    rig.copper_boundary.thickness.value_m = 0.002
    rig.copper_boundary.gap_width.value_m = 0.005
    return rig


def test_health_scope():
    response = TestClient(create_app()).get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["solver_execution"] is False


def test_incomplete_rig_is_rejected():
    response = TestClient(create_app()).post(
        "/api/v1/rig/preview", json=RigV1Schema().model_dump(mode="json")
    )
    assert response.status_code == 422
    assert "required_geometry_measurements_missing" in response.json()["detail"]["reasons"]


def test_complete_rig_returns_deterministic_preview():
    client = TestClient(create_app())
    request = complete_rig().model_dump(mode="json")
    first = client.post("/api/v1/rig/preview", json=request)
    second = client.post("/api/v1/rig/preview", json=request)
    assert first.status_code == second.status_code == 200
    payload = first.json()
    assert payload["readiness"]["hardware_fidelity_ready"] is False
    assert payload["scene"]["fidelity"] == "illustrative_geometry"
    assert payload["scene"]["solver_mesh"] is False
    assert len(payload["provenance"]["material_library_fingerprint"]) == 64
    assert payload["scene"]["geometry_fingerprint"] == second.json()["scene"]["geometry_fingerprint"]
