from datetime import datetime, timezone
from pathlib import Path

import pytest

from pvl.experiments.models import ExperimentConfig
from pvl.experiments.package import (
    persist_dc_experiment_package,
    verify_experiment_package_checksums,
)


def experiment_config() -> ExperimentConfig:
    return ExperimentConfig(
        experiment_id="package-test",
        repetitions=2,
        randomization_seed=42,
        material_library_fingerprint="a" * 64,
        rig_definition_fingerprint="b" * 64,
    )


def test_persisted_package_contains_plan_manifests_and_empty_raw_directories(tmp_path: Path):
    package = persist_dc_experiment_package(
        experiment_config(),
        1.5,
        tmp_path,
        created_utc=datetime(2026, 8, 14, tzinfo=timezone.utc),
    )

    root = Path(package.layout.root)
    assert package.manifest.run_count == 18
    assert package.manifest.solver_execution is False
    assert package.manifest.biological_testing is False
    assert Path(package.layout.experiment_json).is_file()
    assert Path(package.layout.run_matrix_json).is_file()
    assert Path(package.layout.package_manifest_json).is_file()
    assert Path(package.layout.checksums_json).is_file()
    assert verify_experiment_package_checksums(root)

    run_roots = sorted(path for path in Path(package.layout.runs_dir).iterdir() if path.is_dir())
    assert len(run_roots) == 18
    for run_root in run_roots:
        assert (run_root / "manifest.json").is_file()
        assert (run_root / "raw").is_dir()
        assert not (run_root / "mesh.msh").exists()
        assert not (run_root / "solver_input.pro").exists()
        assert not (run_root / "fields.vtu").exists()
        assert not (run_root / "solver.json").exists()


def test_same_plan_has_stable_identity_across_storage_roots(tmp_path: Path):
    first = persist_dc_experiment_package(
        experiment_config(),
        1.0,
        tmp_path / "one",
        created_utc=datetime(2026, 8, 14, 0, 0, tzinfo=timezone.utc),
    )
    second = persist_dc_experiment_package(
        experiment_config(),
        1.0,
        tmp_path / "two",
        created_utc=datetime(2026, 8, 14, 1, 0, tzinfo=timezone.utc),
    )
    assert first.manifest.plan_hash == second.manifest.plan_hash
    assert first.manifest.package_id == second.manifest.package_id
    assert first.manifest.package_fingerprint == second.manifest.package_fingerprint


def test_existing_package_is_never_overwritten(tmp_path: Path):
    persist_dc_experiment_package(experiment_config(), 1.0, tmp_path)
    with pytest.raises(FileExistsError):
        persist_dc_experiment_package(experiment_config(), 1.0, tmp_path)


def test_checksum_verifier_detects_tampering(tmp_path: Path):
    package = persist_dc_experiment_package(experiment_config(), 1.0, tmp_path)
    assert verify_experiment_package_checksums(Path(package.layout.root))
    Path(package.layout.experiment_json).write_text("{}", encoding="utf-8")
    assert not verify_experiment_package_checksums(Path(package.layout.root))
