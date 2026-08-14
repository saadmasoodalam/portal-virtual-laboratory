from fastapi.testclient import TestClient

from pvl.api.app import create_app
from pvl.experiments.models import DriveMode
from pvl.rig.schema import RigV1Schema


def test_experiment_template_is_solver_disabled_and_fingerprinted():
    client = TestClient(create_app())
    rig = RigV1Schema()
    response = client.post('/api/v1/experiment/template', json=rig.model_dump(mode='json'))
    assert response.status_code == 200
    payload = response.json()
    assert payload['medium'] == 'air'
    assert payload['copper_boundary_state'] == 'open'
    assert payload['coil_a']['mode'] == 'off'
    assert payload['coil_b']['mode'] == 'off'
    assert len(payload['material_library_fingerprint']) == 64
    assert len(payload['rig_definition_fingerprint']) == 64
    assert payload['biological_testing'] is False


def test_experiment_template_tracks_rig_medium_and_boundary_state():
    client = TestClient(create_app())
    rig = RigV1Schema()
    rig.sample_chamber.medium_material_id = 'saline_0p9_baseline'
    rig.copper_boundary.baseline_open_loop = False
    response = client.post('/api/v1/experiment/template', json=rig.model_dump(mode='json'))
    assert response.status_code == 200
    payload = response.json()
    assert payload['medium'] == 'saline_0p9'
    assert payload['copper_boundary_state'] == 'closed'


def test_experiment_validation_returns_physics_hash_without_execution():
    client = TestClient(create_app())
    rig = RigV1Schema()
    template = client.post('/api/v1/experiment/template', json=rig.model_dump(mode='json')).json()
    template['coil_a'] = {
        'mode': DriveMode.DC.value,
        'current_a': 1.0,
        'polarity': -1,
        'frequency_hz': None,
        'phase_rad': 0.0,
        'omega_sign': 1,
    }
    response = client.post('/api/v1/experiment/validate', json=template)
    assert response.status_code == 200
    payload = response.json()
    assert payload['accepted'] is True
    assert payload['solver_execution'] is False
    assert len(payload['physics_state_hash']) == 64
    assert payload['experiment']['coil_a']['polarity'] == -1


def test_invalid_dc_zero_current_is_rejected_by_existing_experiment_model():
    client = TestClient(create_app())
    rig = RigV1Schema()
    template = client.post('/api/v1/experiment/template', json=rig.model_dump(mode='json')).json()
    template['coil_a']['mode'] = 'dc'
    response = client.post('/api/v1/experiment/validate', json=template)
    assert response.status_code == 422
