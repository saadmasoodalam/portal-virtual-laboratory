from pathlib import Path

import pytest

from pvl.experiments.models import BoundaryCircuitState, ExperimentConfig, SampleMedium
from pvl.geometry.exploratory import architecture_example_rig_v1
from pvl.materials.library import load_builtin_material_library
from pvl.rig.fingerprint import rig_definition_fingerprint
from pvl.sweeps.dc import DcSweepDefinition, NumericRange, plan_dc_sweep
from pvl.sweeps.package import persist_dc_sweep_plan, verify_dc_sweep_plan


def _plan():
    rig = architecture_example_rig_v1()
    materials = load_builtin_material_library()
    experiment = ExperimentConfig(
        experiment_id="sweep-package-base",
        repetitions=1,
        material_library_fingerprint=materials.fingerprint_sha256(),
        rig_definition_fingerprint=rig_definition_fingerprint(rig),
    )
    definition = DcSweepDefinition(
        sweep_id="sweep-package",
        coil_a_current_a=NumericRange(start=-0.5, stop=0.5, step=0.5),
        coil_b_current_a=NumericRange(start=0.0, stop=0.0, step=1.0),
        media=(SampleMedium.AIR, SampleMedium.SALINE_0P9),
        copper_boundary_states=(BoundaryCircuitState.OPEN, BoundaryCircuitState.CLOSED),
    )
    return plan_dc_sweep(definition, base_rig=rig, base_experiment=experiment, materials=materials)


def test_dc_sweep_plan_persists_without_solver_output_and_verifies_checksums(tmp_path: Path):
    plan = _plan()
    persisted = persist_dc_sweep_plan(plan, tmp_path)
    assert persisted.root.is_dir()
    assert persisted.plan_path.is_file()
    assert persisted.manifest_path.is_file()
    assert persisted.checksums_path.is_file()
    assert verify_dc_sweep_plan(persisted.root)
    assert not (persisted.root / "mesh.msh").exists()
    assert not (persisted.root / "solver_input.pro").exists()
    assert not (persisted.root / "fields.vtu").exists()
    assert set(persisted.checksums) == {"manifest.json", "plan.json"}


def test_dc_sweep_package_is_no_overwrite_and_tamper_evident(tmp_path: Path):
    plan = _plan()
    persisted = persist_dc_sweep_plan(plan, tmp_path)
    with pytest.raises(FileExistsError, match="already exists"):
        persist_dc_sweep_plan(plan, tmp_path)
    persisted.plan_path.write_text("{}", encoding="utf-8")
    assert not verify_dc_sweep_plan(persisted.root)
