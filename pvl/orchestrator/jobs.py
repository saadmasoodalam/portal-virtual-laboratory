from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pvl.core.models import FrozenModel
from pvl.geometry.gmsh_rig import RigGmshConfig
from pvl.materials.library import MaterialLibrary
from pvl.orchestrator.execution import (
    PackageIntegrityError,
    _canonical_sha256,
    _validate_package_identity,
)
from pvl.orchestrator.matrix_execution import MatrixExecutionError, execute_persisted_dc_matrix
from pvl.orchestrator.preflight import PreflightReport, SolverRoute
from pvl.rig.fingerprint import rig_definition_fingerprint
from pvl.rig.schema import RigV1Schema
from pvl.solvers.getdp.runner import ExecutableSet


class JobState(StrEnum):
    PLANNED = "planned"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SimulationJob(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str
    configuration_hash: str
    physics_state_hash: str
    solver_route: SolverRoute
    state: JobState = JobState.PLANNED
    result_root: str
    message: str = ""


def job_from_preflight(
    *,
    job_id: str,
    configuration_hash: str,
    physics_state_hash: str,
    result_root: str,
    preflight: PreflightReport,
) -> SimulationJob:
    if not preflight.ready:
        raise ValueError("simulation job cannot become ready before preflight passes")
    return SimulationJob(
        job_id=job_id,
        configuration_hash=configuration_hash,
        physics_state_hash=physics_state_hash,
        solver_route=preflight.solver_route,
        state=JobState.READY,
        result_root=result_root,
    )


def transition_job(job: SimulationJob, target: JobState, message: str = "") -> SimulationJob:
    allowed = {
        JobState.READY: {JobState.RUNNING, JobState.FAILED},
        JobState.RUNNING: {JobState.COMPLETED, JobState.FAILED},
        JobState.COMPLETED: set(),
        JobState.FAILED: set(),
        JobState.PLANNED: set(),
    }
    if target not in allowed[job.state]:
        raise ValueError(f"invalid job transition: {job.state} -> {target}")
    return job.model_copy(update={"state": target, "message": message})


MATRIX_JOB_SCHEMA_VERSION = "pvl-dc-matrix-job-v1"


class MatrixJobError(RuntimeError):
    pass


class MatrixJobRequest(FrozenModel):
    schema_version: Literal["pvl-dc-matrix-job-v1"] = MATRIX_JOB_SCHEMA_VERSION
    job_id: str
    job_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    experiment_id: str
    package_id: str
    package_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    plan_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_count: int = Field(gt=0)
    rig_definition_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    material_library_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    mesh_configuration_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    mesh_configuration: RigGmshConfig
    rig: RigV1Schema
    created_utc: datetime
    sequential_execution: Literal[True] = True
    max_concurrent_solver_jobs: Literal[1] = 1
    biological_testing: Literal[False] = False
    hypothesis_analysis: Literal[False] = False

    @model_validator(mode="after")
    def validate_request(self) -> "MatrixJobRequest":
        if self.created_utc.tzinfo is None or self.created_utc.utcoffset() != timezone.utc.utcoffset(self.created_utc):
            raise ValueError("matrix job created_utc must be timezone-aware UTC")
        if rig_definition_fingerprint(self.rig) != self.rig_definition_fingerprint:
            raise ValueError("matrix job Rig snapshot does not match its fingerprint")
        if self.mesh_configuration.configuration_hash() != self.mesh_configuration_hash:
            raise ValueError("matrix job mesh snapshot does not match its hash")
        return self


class MatrixJobEvent(FrozenModel):
    schema_version: Literal["pvl-dc-matrix-job-v1"] = MATRIX_JOB_SCHEMA_VERSION
    sequence: int = Field(ge=0)
    status: Literal["queued", "running", "succeeded", "failed"]
    captured_utc: datetime
    message: str
    matrix_result_path: str | None = None
    failure_evidence_path: str | None = None
    error_type: str | None = None

    @model_validator(mode="after")
    def validate_event(self) -> "MatrixJobEvent":
        if self.captured_utc.tzinfo is None or self.captured_utc.utcoffset() != timezone.utc.utcoffset(self.captured_utc):
            raise ValueError("matrix job event timestamp must be timezone-aware UTC")
        if self.status == "succeeded" and not self.matrix_result_path:
            raise ValueError("succeeded matrix job event requires matrix result path")
        if self.status == "failed" and not self.error_type:
            raise ValueError("failed matrix job event requires error type")
        return self


class MatrixJobStatus(FrozenModel):
    request: MatrixJobRequest
    latest_event: MatrixJobEvent
    event_count: int = Field(gt=0)


class MatrixJobPaths(FrozenModel):
    root: str
    request_json: str
    request_sha256: str
    events_dir: str
    claim_file: str


def _matrix_job_paths(results_root: Path, experiment_id: str, job_id: str) -> MatrixJobPaths:
    root = results_root / experiment_id / "jobs" / job_id
    return MatrixJobPaths(
        root=str(root),
        request_json=str(root / "request.json"),
        request_sha256=str(root / "request.sha256"),
        events_dir=str(root / "events"),
        claim_file=str(root / "claim.json"),
    )


def _matrix_request_bytes(request: MatrixJobRequest) -> bytes:
    return json.dumps(
        request.model_dump(mode="json"),
        indent=2,
        sort_keys=True,
    ).encode("utf-8")


def _matrix_event_path(events_dir: Path, sequence: int, status: str) -> Path:
    return events_dir / f"{sequence:06d}-{status}.json"


def _write_matrix_event_exclusive(path: Path, event: MatrixJobEvent) -> None:
    payload = json.dumps(event.model_dump(mode="json"), indent=2, sort_keys=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(payload)


def enqueue_dc_matrix_job(
    *,
    package_root: Path,
    rig: RigV1Schema,
    materials: MaterialLibrary,
    results_root: Path,
    mesh_config: RigGmshConfig,
    created_utc: datetime | None = None,
) -> MatrixJobStatus:
    package, base_config, _ = _validate_package_identity(package_root)
    actual_rig_fingerprint = rig_definition_fingerprint(rig)
    if actual_rig_fingerprint != base_config.rig_definition_fingerprint:
        raise PackageIntegrityError("matrix job Rig fingerprint does not match immutable experiment package")
    material_fingerprint = materials.fingerprint_sha256()
    if material_fingerprint != base_config.material_library_fingerprint:
        raise PackageIntegrityError("matrix job material library does not match immutable experiment package")
    mesh_hash = mesh_config.configuration_hash()
    fingerprint = _canonical_sha256(
        {
            "schema_version": MATRIX_JOB_SCHEMA_VERSION,
            "experiment_id": package.experiment_id,
            "package_id": package.package_id,
            "package_fingerprint": package.package_fingerprint,
            "plan_hash": package.plan_hash,
            "run_ids": list(package.run_ids),
            "rig_definition_fingerprint": actual_rig_fingerprint,
            "material_library_fingerprint": material_fingerprint,
            "mesh_configuration_hash": mesh_hash,
            "sequential_execution": True,
            "max_concurrent_solver_jobs": 1,
            "biological_testing": False,
            "hypothesis_analysis": False,
        }
    )
    job_id = f"matrix-job-{fingerprint[:16]}"
    paths = _matrix_job_paths(results_root, package.experiment_id, job_id)
    root = Path(paths.root)
    if root.exists():
        raise FileExistsError(f"matrix job already exists: {job_id}")
    captured = created_utc or datetime.now(timezone.utc)
    request = MatrixJobRequest(
        job_id=job_id,
        job_fingerprint=fingerprint,
        experiment_id=package.experiment_id,
        package_id=package.package_id,
        package_fingerprint=package.package_fingerprint,
        plan_hash=package.plan_hash,
        run_count=package.run_count,
        rig_definition_fingerprint=actual_rig_fingerprint,
        material_library_fingerprint=material_fingerprint,
        mesh_configuration_hash=mesh_hash,
        mesh_configuration=mesh_config,
        rig=rig,
        created_utc=captured,
    )
    root.mkdir(parents=True, exist_ok=False)
    events_dir = Path(paths.events_dir)
    events_dir.mkdir()
    request_bytes = _matrix_request_bytes(request)
    Path(paths.request_json).write_bytes(request_bytes)
    Path(paths.request_sha256).write_text(sha256(request_bytes).hexdigest() + "\n", encoding="ascii")
    queued = MatrixJobEvent(
        sequence=0,
        status="queued",
        captured_utc=captured,
        message="DC matrix job queued; no solver has executed yet",
    )
    _write_matrix_event_exclusive(_matrix_event_path(events_dir, 0, "queued"), queued)
    return MatrixJobStatus(request=request, latest_event=queued, event_count=1)


def load_matrix_job_status(
    *,
    results_root: Path,
    experiment_id: str,
    job_id: str,
) -> MatrixJobStatus:
    paths = _matrix_job_paths(results_root, experiment_id, job_id)
    request_path = Path(paths.request_json)
    digest_path = Path(paths.request_sha256)
    events_dir = Path(paths.events_dir)
    if not request_path.is_file() or not digest_path.is_file() or not events_dir.is_dir():
        raise FileNotFoundError(f"matrix job not found: {job_id}")
    request_bytes = request_path.read_bytes()
    expected_digest = digest_path.read_text(encoding="ascii").strip()
    if sha256(request_bytes).hexdigest() != expected_digest:
        raise PackageIntegrityError("matrix job request checksum verification failed")
    request = MatrixJobRequest.model_validate(json.loads(request_bytes))
    if request.job_id != job_id or request.experiment_id != experiment_id:
        raise PackageIntegrityError("matrix job request identity mismatch")
    event_paths = sorted(events_dir.glob("*.json"))
    if not event_paths:
        raise PackageIntegrityError("matrix job has no status events")
    events = [
        MatrixJobEvent.model_validate(json.loads(path.read_text(encoding="utf-8")))
        for path in event_paths
    ]
    if [event.sequence for event in events] != list(range(len(events))):
        raise PackageIntegrityError("matrix job event sequence is incomplete or non-contiguous")
    terminal = [event for event in events if event.status in {"succeeded", "failed"}]
    if terminal and terminal[-1] is not events[-1]:
        raise PackageIntegrityError("matrix job contains events after a terminal state")
    return MatrixJobStatus(request=request, latest_event=events[-1], event_count=len(events))


def run_queued_dc_matrix_job(
    *,
    results_root: Path,
    experiment_id: str,
    job_id: str,
    materials: MaterialLibrary,
    executables: ExecutableSet | None = None,
    matrix_executor=execute_persisted_dc_matrix,
) -> MatrixJobStatus:
    status = load_matrix_job_status(results_root=results_root, experiment_id=experiment_id, job_id=job_id)
    if status.latest_event.status != "queued":
        raise MatrixJobError(f"matrix job is not queued: {status.latest_event.status}")
    request = status.request
    if materials.fingerprint_sha256() != request.material_library_fingerprint:
        raise PackageIntegrityError("worker material library does not match queued matrix job")
    package_root = results_root / request.experiment_id / "packages" / request.package_id
    package, _, _ = _validate_package_identity(package_root)
    if package.package_fingerprint != request.package_fingerprint or package.plan_hash != request.plan_hash:
        raise PackageIntegrityError("queued matrix job package identity changed before execution")

    paths = _matrix_job_paths(results_root, experiment_id, job_id)
    claim_path = Path(paths.claim_file)
    claim_payload = {
        "job_id": job_id,
        "claimed_utc": datetime.now(timezone.utc).isoformat(),
        "single_worker_claim": True,
    }
    try:
        with claim_path.open("x", encoding="utf-8") as handle:
            json.dump(claim_payload, handle, indent=2, sort_keys=True)
    except FileExistsError as exc:
        raise MatrixJobError("matrix job already has a worker claim") from exc

    events_dir = Path(paths.events_dir)
    running = MatrixJobEvent(
        sequence=status.event_count,
        status="running",
        captured_utc=datetime.now(timezone.utc),
        message="single worker claimed job; sequential DC matrix execution started",
    )
    _write_matrix_event_exclusive(_matrix_event_path(events_dir, running.sequence, "running"), running)

    try:
        matrix_result = matrix_executor(
            package_root=package_root,
            rig=request.rig,
            materials=materials,
            results_root=results_root,
            mesh_config=request.mesh_configuration,
            executables=executables,
        )
    except Exception as exc:
        evidence_root = exc.evidence_root if isinstance(exc, MatrixExecutionError) else None
        relative_evidence = None
        if evidence_root:
            try:
                relative_evidence = str(Path(evidence_root).relative_to(results_root))
            except ValueError:
                relative_evidence = str(evidence_root)
        failed = MatrixJobEvent(
            sequence=running.sequence + 1,
            status="failed",
            captured_utc=datetime.now(timezone.utc),
            message=str(exc),
            failure_evidence_path=relative_evidence,
            error_type=type(exc).__name__,
        )
        _write_matrix_event_exclusive(_matrix_event_path(events_dir, failed.sequence, "failed"), failed)
        return load_matrix_job_status(results_root=results_root, experiment_id=experiment_id, job_id=job_id)

    succeeded = MatrixJobEvent(
        sequence=running.sequence + 1,
        status="succeeded",
        captured_utc=datetime.now(timezone.utc),
        message="all persisted DC matrix runs completed",
        matrix_result_path=str(Path(matrix_result.root).relative_to(results_root)),
    )
    _write_matrix_event_exclusive(_matrix_event_path(events_dir, succeeded.sequence, "succeeded"), succeeded)
    return load_matrix_job_status(results_root=results_root, experiment_id=experiment_id, job_id=job_id)
