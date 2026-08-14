from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from pvl.experiments.models import ExperimentConfig
from pvl.experiments.package import (
    persist_dc_experiment_package,
    verify_experiment_package_checksums,
)
from pvl.geometry.exploratory import architecture_example_rig_v1
from pvl.materials.library import load_builtin_material_library
from pvl.orchestrator.scientific_execution import (
    execute_and_persist_single_run,
    exploratory_complete_rig_dc_mesh_profile,
)
from pvl.rig.fingerprint import rig_definition_fingerprint


def _package(tmp_path: Path):
    rig = architecture_example_rig_v1()
    materials = load_builtin_material_library()
    config = ExperimentConfig(
        experiment_id="scientific-run-test",
        repetitions=1,
        randomization_seed=7,
        material_library_fingerprint=materials.fingerprint_sha256(),
        rig_definition_fingerprint=rig_definition_fingerprint(rig),
    )
    package = persist_dc_experiment_package(
        config,
        1.0,
        tmp_path,
        created_utc=datetime(2026, 8, 15, 0, 0, tzinfo=timezone.utc),
    )
    matrix = json.loads(Path(package.layout.run_matrix_json).read_text(encoding="utf-8"))
    return rig, materials, package, matrix


def _fake_magnetostatic_runner(experiment, topology, materials, mesh_config, output_dir, **kwargs):
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "mesh.msh").write_text("fake mesh evidence", encoding="utf-8")
    (output_dir / "solver_input.pro").write_text("fake solver evidence", encoding="utf-8")
    (output_dir / "solver_stdout.log").write_text("fake solver stdout", encoding="utf-8")
    return SimpleNamespace(
        metrics={
            "axis_peak_abs_b_t": 0.012,
            "axis_rms_b_t": 0.006,
            "axis_center_b_y_t": 0.010,
            "probe_peak_abs_b_t": 0.011,
            "probe_center_b_y_t": 0.010,
        },
        solver_versions={"gmsh": "test-gmsh", "getdp": "test-getdp"},
    )


def test_active_dc_run_persists_solver_evidence_without_mutating_package(tmp_path: Path):
    rig, materials, package, matrix = _package(tmp_path)
    active = next(row for row in matrix if row["state_id"] != "off_off")
    package_root = Path(package.layout.root)
    original_package_checksums = Path(package.layout.checksums_json).read_text(encoding="utf-8")

    result = execute_and_persist_single_run(
        package_root=package_root,
        run_id=active["run_id"],
        rig=rig,
        materials=materials,
        results_root=tmp_path,
        mesh_config=exploratory_complete_rig_dc_mesh_profile(),
        created_utc=datetime(2026, 8, 15, 1, 0, tzinfo=timezone.utc),
        magnetostatic_runner=_fake_magnetostatic_runner,
    )

    root = Path(result.root)
    assert result.manifest.solver_route.value == "magnetostatic"
    assert result.manifest.solver_execution is True
    assert result.manifest.package_integrity_verified is True
    assert result.manifest.single_run_only is True
    assert result.manifest.batch_execution is False
    assert result.manifest.biological_testing is False
    assert result.manifest.hypothesis_analysis is False
    assert result.manifest.physical_validation is False
    assert (root / "experiment.json").is_file()
    assert (root / "geometry.json").is_file()
    assert (root / "materials.json").is_file()
    assert (root / "solver.json").is_file()
    assert (root / "metrics.json").is_file()
    assert (root / "summary.csv").is_file()
    assert (root / "environment.json").is_file()
    assert (root / "job_manifest.json").is_file()
    assert (root / "checksums.json").is_file()
    assert (root / "raw" / "mesh.msh").is_file()
    assert (root / "raw" / "solver_input.pro").is_file()
    assert verify_experiment_package_checksums(package_root)
    assert Path(package.layout.checksums_json).read_text(encoding="utf-8") == original_package_checksums


def test_off_off_control_is_persisted_without_invoking_solver(tmp_path: Path):
    rig, materials, package, matrix = _package(tmp_path)
    control = next(row for row in matrix if row["state_id"] == "off_off")

    def forbidden_runner(*args, **kwargs):
        raise AssertionError("OFF/OFF control must not invoke GetDP")

    result = execute_and_persist_single_run(
        package_root=Path(package.layout.root),
        run_id=control["run_id"],
        rig=rig,
        materials=materials,
        results_root=tmp_path,
        mesh_config=exploratory_complete_rig_dc_mesh_profile(),
        created_utc=datetime(2026, 8, 15, 1, 0, tzinfo=timezone.utc),
        magnetostatic_runner=forbidden_runner,
    )
    assert result.manifest.solver_route.value == "control"
    assert result.manifest.solver_execution is False
    assert Path(result.root, "raw").is_dir()
    assert not any(Path(result.root, "raw").iterdir())


def test_same_scientific_execution_identity_is_never_overwritten(tmp_path: Path):
    rig, materials, package, matrix = _package(tmp_path)
    active = next(row for row in matrix if row["state_id"] != "off_off")
    kwargs = dict(
        package_root=Path(package.layout.root),
        run_id=active["run_id"],
        rig=rig,
        materials=materials,
        results_root=tmp_path,
        mesh_config=exploratory_complete_rig_dc_mesh_profile(),
        magnetostatic_runner=_fake_magnetostatic_runner,
    )
    execute_and_persist_single_run(**kwargs)
    with pytest.raises(FileExistsError, match="already exists"):
        execute_and_persist_single_run(**kwargs)
