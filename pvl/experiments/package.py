from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import shutil
from typing import Literal
from uuid import uuid4

from pydantic import Field, model_validator

from pvl.core.models import FrozenModel
from pvl.experiments.export import write_experiment_plan
from pvl.experiments.models import ExperimentConfig, RunManifest, RunStatus
from pvl.experiments.planning import PlannedRun, plan_rig_v1_dc_experiment
from pvl.experiments.storage import (
    ExperimentPackageLayout,
    experiment_package_layout,
    initialize_run_storage,
    package_run_storage_layout,
)


PACKAGE_SCHEMA_VERSION = "pvl-experiment-package-v1"


class ExperimentPackageManifest(FrozenModel):
    schema_version: Literal["pvl-experiment-package-v1"] = PACKAGE_SCHEMA_VERSION
    package_id: str
    experiment_id: str
    plan_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    package_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    configuration_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    physics_state_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_count: int = Field(ge=1)
    created_utc: datetime
    solver_execution: Literal[False] = False
    biological_testing: Literal[False] = False
    run_ids: tuple[str, ...]
    required_future_run_artifacts: tuple[str, ...] = (
        "geometry.json",
        "materials.json",
        "solver.json",
        "mesh.msh",
        "solver_input.pro",
        "solver_stdout.log",
        "solver_stderr.log",
        "raw/",
        "fields.vtu",
        "metrics.json",
        "summary.csv",
        "environment.json",
    )

    @model_validator(mode="after")
    def validate_created_utc(self) -> "ExperimentPackageManifest":
        if self.created_utc.tzinfo is None or self.created_utc.utcoffset() != timezone.utc.utcoffset(self.created_utc):
            raise ValueError("created_utc must be timezone-aware UTC")
        if len(self.run_ids) != self.run_count:
            raise ValueError("run_ids length must equal run_count")
        return self


class PersistedExperimentPackage(FrozenModel):
    layout: ExperimentPackageLayout
    manifest: ExperimentPackageManifest
    checksums: dict[str, str]


def planned_run_record(run: PlannedRun) -> dict[str, object]:
    return {
        "run_id": run.run_id,
        "sequence_index": run.sequence_index,
        "repetition_index": run.repetition_index,
        "state_id": run.state_id,
        "configuration_hash": run.configuration.configuration_hash(),
        "physics_state_hash": run.configuration.physics_state_hash(),
        "coil_a": run.configuration.coil_a.model_dump(mode="json"),
        "coil_b": run.configuration.coil_b.model_dump(mode="json"),
    }


def experiment_plan_hash(runs: tuple[PlannedRun, ...]) -> str:
    canonical = json.dumps(
        [planned_run_record(run) for run in runs],
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


def experiment_package_fingerprint(config: ExperimentConfig, plan_hash: str, run_count: int) -> str:
    payload = {
        "schema_version": PACKAGE_SCHEMA_VERSION,
        "configuration_hash": config.configuration_hash(),
        "physics_state_hash": config.physics_state_hash(),
        "plan_hash": plan_hash,
        "run_count": run_count,
        "solver_execution": False,
        "biological_testing": False,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return sha256(canonical.encode("utf-8")).hexdigest()


def experiment_package_id(config: ExperimentConfig, plan_hash: str) -> str:
    return f"{config.experiment_id}-{plan_hash[:16]}"


def _relative_run_paths(package_root: Path, layout) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in layout.model_dump(mode="json").items():
        if key == "root":
            continue
        result[key] = str(Path(value).relative_to(package_root))
    return result


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _collect_checksums(root: Path) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file() and item.name != "checksums.json"):
        checksums[str(path.relative_to(root))] = _file_sha256(path)
    return checksums


def verify_experiment_package_checksums(package_root: Path) -> bool:
    checksum_path = package_root / "checksums.json"
    if not checksum_path.is_file():
        return False
    expected = json.loads(checksum_path.read_text(encoding="utf-8"))
    if not isinstance(expected, dict):
        return False
    for relative_path, expected_hash in expected.items():
        if not isinstance(relative_path, str) or not isinstance(expected_hash, str):
            return False
        path = package_root / relative_path
        if not path.is_file() or _file_sha256(path) != expected_hash:
            return False
    return set(expected) == set(_collect_checksums(package_root))


def persist_dc_experiment_package(
    config: ExperimentConfig,
    current_a: float,
    results_root: Path,
    *,
    created_utc: datetime | None = None,
) -> PersistedExperimentPackage:
    planned = plan_rig_v1_dc_experiment(config, current_a)
    plan_hash = experiment_plan_hash(planned)
    package_id = experiment_package_id(config, plan_hash)
    final_layout = experiment_package_layout(results_root, config.experiment_id, package_id)
    final_root = Path(final_layout.root)
    if final_root.exists():
        raise FileExistsError(f"experiment package already exists: {package_id}")

    created = created_utc or datetime.now(timezone.utc)
    if created.tzinfo is None or created.utcoffset() != timezone.utc.utcoffset(created):
        raise ValueError("created_utc must be timezone-aware UTC")

    final_root.parent.mkdir(parents=True, exist_ok=True)
    staging_root = final_root.parent / f".{package_id}.staging-{uuid4().hex}"
    staging_layout = ExperimentPackageLayout(
        root=str(staging_root),
        experiment_json=str(staging_root / "experiment.json"),
        run_matrix_json=str(staging_root / "run_matrix.json"),
        package_manifest_json=str(staging_root / "package_manifest.json"),
        checksums_json=str(staging_root / "checksums.json"),
        runs_dir=str(staging_root / "runs"),
    )

    try:
        staging_root.mkdir(parents=True, exist_ok=False)
        Path(staging_layout.runs_dir).mkdir()
        write_experiment_plan(config, planned, staging_root)

        for run in planned:
            run_layout = package_run_storage_layout(staging_layout, run.run_id)
            run_manifest = RunManifest(
                run_id=run.run_id,
                experiment_id=config.experiment_id,
                repetition_index=run.repetition_index,
                randomized_sequence_index=run.sequence_index,
                planned_configuration_hash=run.configuration.configuration_hash(),
                physics_state_hash=run.configuration.physics_state_hash(),
                rig_definition_fingerprint=config.rig_definition_fingerprint,
                material_library_fingerprint=config.material_library_fingerprint,
                created_utc=created,
                status=RunStatus.PLANNED,
                solver_versions={},
                paths=_relative_run_paths(staging_root, run_layout),
            )
            initialize_run_storage(run_layout, run_manifest)

        manifest = ExperimentPackageManifest(
            package_id=package_id,
            experiment_id=config.experiment_id,
            plan_hash=plan_hash,
            package_fingerprint=experiment_package_fingerprint(config, plan_hash, len(planned)),
            configuration_hash=config.configuration_hash(),
            physics_state_hash=config.physics_state_hash(),
            run_count=len(planned),
            created_utc=created,
            run_ids=tuple(run.run_id for run in planned),
        )
        _write_json(Path(staging_layout.package_manifest_json), manifest.model_dump(mode="json"))
        checksums = _collect_checksums(staging_root)
        _write_json(Path(staging_layout.checksums_json), checksums)
        staging_root.rename(final_root)
    except Exception:
        shutil.rmtree(staging_root, ignore_errors=True)
        raise

    return PersistedExperimentPackage(layout=final_layout, manifest=manifest, checksums=checksums)
