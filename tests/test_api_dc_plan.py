from fastapi.testclient import TestClient

from pvl.api.app import create_app
from pvl.rig.schema import RigV1Schema


EXPECTED_STATES = {
    'off_off',
    'a_positive',
    'a_negative',
    'b_positive',
    'b_negative',
    'both_same_positive',
    'both_same_negative',
    'both_opposed_ab',
    'both_opposed_ba',
}


def experiment_template(client: TestClient, *, seed: int = 42, repetitions: int = 3) -> dict:
    rig = RigV1Schema()
    payload = client.post('/api/v1/experiment/template', json=rig.model_dump(mode='json')).json()
    payload['randomization_seed'] = seed
    payload['repetitions'] = repetitions
    return payload


def test_dc_plan_has_complete_repeated_control_matrix_without_execution():
    client = TestClient(create_app())
    experiment = experiment_template(client)
    response = client.post('/api/v1/experiment/plan/dc', json={'experiment': experiment, 'current_a': 1.25})
    assert response.status_code == 200
    payload = response.json()
    assert payload['solver_execution'] is False
    assert payload['run_count'] == 27
    assert payload['repetitions'] == 3
    assert payload['randomization_seed'] == 42
    assert payload['current_a'] == 1.25
    assert len(payload['plan_hash']) == 64

    for repetition in range(1, 4):
        block = [run for run in payload['runs'] if run['repetition_index'] == repetition]
        assert len(block) == 9
        assert block[0]['state_id'] == 'off_off'
        assert {run['state_id'] for run in block} == EXPECTED_STATES
        assert all(len(run['configuration_hash']) == 64 for run in block)
        assert all(len(run['physics_state_hash']) == 64 for run in block)


def test_dc_plan_is_reproducible_for_same_seed_current_and_experiment():
    client = TestClient(create_app())
    experiment = experiment_template(client, seed=7)
    request = {'experiment': experiment, 'current_a': 0.8}
    first = client.post('/api/v1/experiment/plan/dc', json=request).json()
    second = client.post('/api/v1/experiment/plan/dc', json=request).json()
    assert first == second


def test_dc_plan_seed_changes_active_order_but_keeps_off_control_first():
    client = TestClient(create_app())
    first_experiment = experiment_template(client, seed=1, repetitions=1)
    second_experiment = experiment_template(client, seed=2, repetitions=1)
    first = client.post('/api/v1/experiment/plan/dc', json={'experiment': first_experiment, 'current_a': 1.0}).json()
    second = client.post('/api/v1/experiment/plan/dc', json={'experiment': second_experiment, 'current_a': 1.0}).json()
    assert first['runs'][0]['state_id'] == second['runs'][0]['state_id'] == 'off_off'
    assert [run['state_id'] for run in first['runs'][1:]] != [run['state_id'] for run in second['runs'][1:]]
    assert first['plan_hash'] != second['plan_hash']


def test_opposed_dc_plan_uses_polarity_not_signed_frequency():
    client = TestClient(create_app())
    experiment = experiment_template(client, repetitions=1)
    payload = client.post('/api/v1/experiment/plan/dc', json={'experiment': experiment, 'current_a': 1.0}).json()
    opposed = next(run for run in payload['runs'] if run['state_id'] == 'both_opposed_ab')
    assert opposed['coil_a']['polarity'] == 1
    assert opposed['coil_b']['polarity'] == -1
    assert opposed['coil_a']['omega_sign'] == 1
    assert opposed['coil_b']['omega_sign'] == 1
    assert opposed['coil_a']['frequency_hz'] is None
    assert opposed['coil_b']['frequency_hz'] is None


def test_dc_plan_requires_positive_current():
    client = TestClient(create_app())
    experiment = experiment_template(client)
    response = client.post('/api/v1/experiment/plan/dc', json={'experiment': experiment, 'current_a': 0.0})
    assert response.status_code == 422
