from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import platform
import shutil
import sys
from typing import Literal
from uuid import uuid4

from pydantic import Field, model_validator

from pvl.core.models import FrozenModel
from pvl.experiments.models import CoilDriveState, ExperimentConfig, RunManifest
from pvl.experiments.package import (
    ExperimentPackageManifest,
    experiment_package_fingerprint,
    verify_experiment_package_checksums,
)
from pvl.materials.library import MaterialLibrary
from pvl.orchestrator.preflight import PreflightIssue, SolverRoute, preflight_experiment
from pvl.rig.schema import RigV1Schema
from pvl.solvers.getdp.runner import SolverUnavailableError, discover_executables, solver_versions


EXECUTION_SCHEMA_VERSION = "pvl-single-run-execution-gate-v1"


class PackageIntegrityError(RuntimeError):
    """Raised when an immutable PVL experiment package cannot be trusted."""


class PlannedRunNotFoundError(LookupError):
    """Raised when the deliberately selected run is absent from a package."""


class ExecutionGateIssue(FrozenModel):
    code: str
    message: str


class EnvironmentMetadata(FrozenModel):
    captured_utc: datetime
    python_version: str
    platform: str
    machine: str
    processor: str
    solver_versions: dict[str, str] = Field(default_factory=dict)
    solver_stack_available: bool

    @model_validator(mode="after")
    def require_utc_timestamp(self) -> "EnvironmentMetadata":
        if self.captured_utc.tzinfo is None or self.captured_utc.utcoffset() != timezone.utc.utcoffset(self.captured_utc):
            raise ValueError("captured_utc must be timezone-aware UTC")
        return self


class SingleRunExecutionManifest(FrozenModel):
    schema_version: Literal["pvl-single-run-execution-gate-v1"] = EXECUTION_SCHEMA_VERSION
    job_id: str
    job_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    package_id: str
    package_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    plan_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_id: str
    planned_configuration_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    physics_state_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    rig_definition_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    material_library_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    solver_route: SolverRoute
    created_utc: datetime
    package_integrity_verified: Literal[True] = True
    preflight_ready: bool
    execution_allowed: bool
    solver_execution: bool = False
    single_run_only: Literal[True] = True
    batch_execution: Literal[False] = False
    biological_testing: Literal[False] = False
    issues: tuple[ExecutionGateIssue, ...] = ()
    solver_versions: dict[str, str] = Field(default_factory=dict)
    environment_file: str = "environment.json"

    @model_validator(mode="after")
    def require_utc_timestamp(self) -> "SingleRunExecutionManifest":
        if self.created_utc.tzinfo is None or self.created_utc.utcoffset() != timezone.utc.utcoffset(self.created_utc):
            raise ValueError("created_utc must be timezone-aware UTC")
        if self.solver_execution and not self.execution_allowed:
            raise ValueError("solver execution cannot be true when execution is blocked")
        return self


class PersistedExecutionGate(FrozenModel):
    root: str
    manifest: SingleRunExecutionManifest
    checksums: dict[str, str]


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PackageIntegrityError(f"cannot read trusted package JSON: {path.name}") from exc


def _canonical_sha256(payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return sha256(canonical.encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _collect_checksums(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): _file_sha256(path)
        for path in sorted(item for item in root.rglob("*") if item.is_file() and item.name != "checksums.json")
    }


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _capture_environment(captured_utc: datetime) -> EnvironmentMetadata:
    versions: dict[str, str] = {}
    available = False
    try:
        executable_set = discover_executables()
        detected = solver_versions(executable_set)
        versions = {"gmsh": detected.gmsh, "getdp": detected.getdp}
        available = True
    except SolverUnavailableError:
        pass
    return EnvironmentMetadata(
        captured_utc=captured_utc,
        python_version=sys.version.split()[0],
        platform=platform.platform(),
        machine=platform.machine(),
        processor=platform.processor(),
        solver_versions=versions,
        solver_stack_available=available,
    )


def _validate_package_identity(
    package_root: Path,
) -> tuple[ExperimentPackageManifest, ExperimentConfig, list[dict[str, object]]]:
    if not package_root.is_dir():
        raise FileNotFoundError(f"experiment package not found: {package_root}")
    if not verify_experiment_package_checksums(package_root):
        raise PackageIntegrityError("experiment package checksum verification failed")

    manifest = ExperimentPackageManifest.model_validate(_read_json(package_root / "package_manifest.json"))
    experiment_payload = _read_json(package_root / "experiment.json")
    matrix_payload = _read_json(package_root / "run_matrix.json")
    if not isinstance(experiment_payload, dict) or not isinstance(matrix_payload, list):
        raise PackageIntegrityError("experiment package JSON structure is invalid")

    try:
        config = ExperimentConfig.model_validate(experiment_payload["configuration"])
    except (KeyError, TypeError, ValueError) as exc:
        raise PackageIntegrityError("experiment configuration is invalid") from exc
    matrix: list[dict[str, object]] = []
    for row in matrix_payload:
        if not isinstance(row, dict):
            raise PackageIntegrityError("run matrix contains a non-object record")
        matrix.append(row)

    if experiment_payload.get("configuration_hash") != config.configuration_hash():
        raise PackageIntegrityError("experiment configuration hash mismatch")
    if experiment_payload.get("physics_state_hash") != config.physics_state_hash():
        raise PackageIntegrityError("experiment physics-state hash mismatch")
    if manifest.configuration_hash != config.configuration_hash():
        raise PackageIntegrityError("package manifest configuration hash mismatch")
    if manifest.physics_state_hash != config.physics_state_hash():
        raise PackageIntegrityError("package manifest physics-state hash mismatch")
    if manifest.run_count != len(matrix):
        raise PackageIntegrityError("package manifest run count does not match run matrix")
    if tuple(str(row.get("run_id")) for row in matrix) != manifest.run_ids:
        raise PackageIntegrityError("package manifest run ordering does not match run matrix")
    if _canonical_sha256(matrix) != manifest.plan_hash:
        raise PackageIntegrityError("package plan hash does not match run matrix")
    expected_fingerprint = experiment_package_fingerprint(config, manifest.plan_hash, manifest.run_count)
    if expected_fingerprint != manifest.package_fingerprint:
        raise PackageIntegrityError("package fingerprint mismatch")
    return manifest, config, matrix


def _selected_run_configuration(
    package_root: Path,
    base_config: ExperimentConfig,
    matrix: list[dict[str, object]],
    run_id: str,
) -> ExperimentConfig:
    matches = [row for row in matrix if row.get("run_id") == run_id]
    if len(matches) != 1:
        raise PlannedRunNotFoundError(f"planned run not found or not unique: {run_id}")
    row = matches[0]
    try:
        selected = base_config.model_copy(
            update={
                "coil_a": CoilDriveState.model_validate(row["coil_a"]),
                "coil_b": CoilDriveState.model_validate(row["coil_b"]),
            }
        )
        run_manifest = RunManifest.model_validate(
            _read_json(package_root / "runs" / run_id / "manifest.json")
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise PackageIntegrityError("selected planned run record is invalid") from exc

    configuration_hash = selected.configuration_hash()
    physics_state_hash = selected.physics_state_hash()
    if row.get("configuration_hash") != configuration_hash:
        raise PackageIntegrityError("selected run configuration hash mismatch")
    if row.get("physics_state_hash") != physics_state_hash:
        raise PackageIntegrityError("selected run physics-state hash mismatch")
    if run_manifest.run_id != run_id:
        raise PackageIntegrityError("selected run manifest ID mismatch")
    if run_manifest.planned_configuration_hash != configuration_hash:
        raise PackageIntegrityError("selected run manifest configuration hash mismatch")
    if run_manifest.physics_state_hash != physics_state_hash:
        raise PackageIntegrityError("selected run manifest physics-state hash mismatch")
    if run_manifest.rig_definition_fingerprint != selected.rig_definition_fingerprint:
        raise PackageIntegrityError("selected run manifest Rig fingerprint mismatch")
    if run_manifest.material_library_fingerprint != selected.material_library_fingerprint:
        raise PackageIntegrityError("selected run manifest material fingerprint mismatch")
    return selected


def _gate_issues(preflight_issues: tuple[PreflightIssue, ...], solver_route: SolverRoute) -> tuple[ExecutionGateIssue, ...]:
    issues = [ExecutionGateIssue(code=issue.code, message=issue.message) for issue in preflight_issues]
    if solver_route == SolverRoute.MAGNETOQUASISTATIC:
        issues.append(ExecutionGateIssue(
            code="complete_rig_magnetoquasistatic_unavailable",
            message=(
                "complete-Rig harmonic/eddy-current execution has not yet passed its dedicated "
                "validation gate; validated POC surrogate geometry must not be substituted"
            ),
        ))
    return tuple(issues)


def _job_fingerprint_payload(
    *,
    package: ExperimentPackageManifest,
    run_config: ExperimentConfig,
    solver_route: SolverRoute,
    preflight_ready: bool,
    execution_allowed: bool,
    issues: tuple[ExecutionGateIssue, ...],
) -> dict[str, object]:
    return {
        "schema_version": EXECUTION_SCHEMA_VERSION,
        "package_id": package.package_id,
        "package_fingerprint": package.package_fingerprint,
        "plan_hash": package.plan_hash,
        "run_configuration_hash": run_config.configuration_hash(),
        "physics_state_hash": run_config.physics_state_hash(),
        "rig_definition_fingerprint": run_config.rig_definition_fingerprint,
        "material_library_fingerprint": run_config.material_library_fingerprint,
        "solver_route": solver_route.value,
        "preflight_ready": preflight_ready,
        "execution_allowed": execution_allowed,
        "issues": [issue.model_dump(mode="json") for issue in issues],
        "single_run_only": True,
        "batch_execution": False,
        "biological_testing": False,
    }


def evaluate_and_persist_single_run_gate(
    *,
    package_root: Path,
    run_id: str,
    rig: RigV1Schema,
    materials: MaterialLibrary,
    results_root: Path,
    created_utc: datetime | None = None,
) -> PersistedExecutionGate:
    """Evaluate one immutable packaged run and persist an auditable execution decision.

    This function never invokes Gmsh/GetDP itself. It verifies package identity and scientific
    preflight, then records whether a separate single-run executor may proceed. OFF/OFF control and
    complete-Rig DC magnetostatic routes are eligible; harmonic complete-Rig execution remains
    blocked until its own solver/validation unit is complete. The immutable package is never modified.
    """
    package, base_config, matrix = _validate_package_identity(package_root)
    run_config = _selected_run_configuration(package_root, base_config, matrix, run_id)
    report = preflight_experiment(run_config, rig, materials)
    issues = _gate_issues(report.issues, report.solver_route)

    execution_allowed = (
        report.ready
        and report.solver_route in {SolverRoute.CONTROL, SolverRoute.MAGNETOSTATIC}
        and not issues
    )
    captured = created_utc or datetime.now(timezone.utc)
    if captured.tzinfo is None or captured.utcoffset() != timezone.utc.utcoffset(captured):
        raise ValueError("created_utc must be timezone-aware UTC")
    environment = _capture_environment(captured)

    fingerprint = _canonical_sha256(_job_fingerprint_payload(
        package=package,
        run_config=run_config,
        solver_route=report.solver_route,
        preflight_ready=report.ready,
        execution_allowed=execution_allowed,
        issues=issues,
    ))
    job_id = f"job-{fingerprint[:16]}"
    manifest = SingleRunExecutionManifest(
        job_id=job_id,
        job_fingerprint=fingerprint,
        package_id=package.package_id,
        package_fingerprint=package.package_fingerprint,
        plan_hash=package.plan_hash,
        run_id=run_id,
        planned_configuration_hash=run_config.configuration_hash(),
        physics_state_hash=run_config.physics_state_hash(),
        rig_definition_fingerprint=run_config.rig_definition_fingerprint,
        material_library_fingerprint=run_config.material_library_fingerprint,
        solver_route=report.solver_route,
        created_utc=captured,
        preflight_ready=report.ready,
        execution_allowed=execution_allowed,
        solver_execution=False,
        issues=issues,
        solver_versions=environment.solver_versions,
    )

    final_root = (
        results_root
        / package.experiment_id
        / "executions"
        / package.package_id
        / run_id
        / job_id
    )
    if final_root.exists():
        raise FileExistsError(f"single-run execution gate already exists: {job_id}")
    final_root.parent.mkdir(parents=True, exist_ok=True)
    staging_root = final_root.parent / f".{job_id}.staging-{uuid4().hex}"
    try:
        staging_root.mkdir(parents=True, exist_ok=False)
        (staging_root / "raw").mkdir()
        _write_json(staging_root / "job_manifest.json", manifest.model_dump(mode="json"))
        _write_json(staging_root / "environment.json", environment.model_dump(mode="json"))
        checksums = _collect_checksums(staging_root)
        _write_json(staging_root / "checksums.json", checksums)
        staging_root.rename(final_root)
    except Exception:
        shutil.rmtree(staging_root, ignore_errors=True)
        raise

    if not verify_experiment_package_checksums(package_root):
        raise PackageIntegrityError("immutable package changed while persisting execution gate")
    return PersistedExecutionGate(root=str(final_root), manifest=manifest, checksums=checksums)
