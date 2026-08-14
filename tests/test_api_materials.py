from fastapi.testclient import TestClient

from pvl.api.app import create_app


def test_material_catalog_exposes_versioned_controlled_choices():
    response = TestClient(create_app()).get('/api/v1/materials')
    assert response.status_code == 200
    payload = response.json()
    ids = {item['material_id'] for item in payload['materials']}
    assert len(payload['library_fingerprint']) == 64
    assert 'air_baseline' in ids
    assert 'distilled_water_baseline' in ids
    assert 'saline_0p9_baseline' in ids
    steel = next(item for item in payload['materials'] if item['material_id'] == 'mild_steel_linear_baseline')
    assert steel['model_kind'] == 'linear_placeholder'
    assert steel['solver_warning']
