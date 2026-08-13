from pathlib import Path

from pvl.experiments.storage import run_storage_layout


def test_run_layout_has_expected_files(tmp_path: Path):
    layout = run_storage_layout(tmp_path, "exp", "run")
    assert layout.experiment_json.endswith("experiment.json")
    assert layout.geometry_json.endswith("geometry.json")
    assert layout.materials_json.endswith("materials.json")
    assert layout.mesh_msh.endswith("mesh.msh")
    assert layout.solver_input_pro.endswith("solver_input.pro")
    assert layout.fields_vtu.endswith("fields.vtu")
    assert layout.metrics_json.endswith("metrics.json")
    assert layout.environment_json.endswith("environment.json")
    assert layout.manifest_json.endswith("manifest.json")
