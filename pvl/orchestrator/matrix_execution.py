from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
from typing import Literal
from uuid import uuid4

from pydantic import Field, model_validator

from pvl.core.models import FrozenModel
from pvl.geometry.gmsh_rig import RigGmshConfig
from pvl.materials.library import MaterialLibrary
from pvl.orchestrator.execution import (
    PackageIntegrityError,
    _canonical_sha256,
    _collect_checksums,
    _read_json,
    _validate_package_identity,
    _write_json,
)
from pvl.orchestrator.preflight import SolverRoute
from pvl.orchestrator.scientific_execution import (
    PersistedScientificRun,
    ScientificRunManifest,
    execute_and_persist_single_run,
)
from pvl.rig.schema import RigV1Schema
from pvl.solvers.getdp.runner import ExecutableSet


MATRIX_EXECUTION_SCHEMA_VERSION = "pvl-dc-matrix-execution-v1"


class MatrixExecutionError(RuntimeError):
    def __init__(self, message: str, *, evidence_root: str | None = None):
        super().__init__(message)
        self.evidence_root = evidence_root


class DcMatrixRunRecord(FrozenModel):
    sequence_index: int = Field(ge=0)
    run_id: str
    state_id: str
    job_id: str
    job_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    solver_route: SolverRoute
    solver_execution: bool
    reused_verified_result: bool = False
    relative_result_path: str


class DcMatrixExecutionManifest(FrozenModel):
    schema_version: Literal["pvl-dc-matrix-execution-v1"] = MATRIX_EXECUTION_SCHEMA_VERSION
    matrix_execution_id: str
    matrix_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    experiment_id: str
    package_id: str
    package_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    plan_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    mesh_configuration_hash: str
    created_utc: datetime
    completed_utc: datetime
    run_count: int = Field(gt=0)
    completed_run_count: int = Field(gt=0)
    sequential_execution: Literal[True] = True
    max_concurrent_solver_jobs: Literal[1] = 1
    randomized_plan_order_preserved: Literal[True] = True
    biological_testing: Literal[False] = False
    hypothesis_analysis: Literal[False] = False
    physical_validation: Literal[False] = False
    runs: tuple[DcMatrixRunRecord, ...]

    @model_validator(mode="after")
    def validate_matrix_completion(self) -> "DcMatrixExecutionManifest":
        for value in (self.created_utc, self.completed_utc):
            if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
                raise ValueError("matrix timestamps must be timezone-aware UTC")
        if self.completed_run_count != self.run_count or len(self.runs) != self.run_count:
            raise ValueError("completed matrix manifest must account for every planned run")
        if tuple(record.sequence_index for record in self.runs) != tuple(range(self.run_count)):
            raise ValueError("matrix run records must preserve exact planned sequence order")
        return self


class PersistedDcMatrixExecution(FrozenModel):
    root: str
    manifest: DcMatrixExecutionManifest
    checksums: dict[str, str]


def _verify_existing_single_run(
    *,
    scientific_root: Path,
    package_id: str,
    run_id: str,
    mesh_configuration_hash: str,
) -> PersistedScientificRun:
    matches: list[PersistedScientificRun] = []
    if scientific_root.is_dir():
        for candidate in sorted(path for path in scientific_root.iterdir() if path.is_dir()):
            manifest_path = candidate / "job_manifest.json"
            checksums_path = candidate / "checksums.json"
            if not manifest_path.is_file() or not checksums_path.is_file():
                continue
            try:
                manifest = ScientificRunManifest.model_validate(_read_json(manifest_path))
                expected = _read_json(checksums_path)
            except (PackageIntegrityError, ValueError, TypeError):
                continue
            if not isinstance(expected, dict):
                continue
            actual = _collect_checksums(candidate)
            if actual != expected:
                continue
            if manifest.package_id != package_id or manifest.run_id != run_id:
                continue
            if manifest.mesh_configuration_hash != mesh_configuration_hash:
                continue
            matches.append(
                PersistedScientificRun(
                    root=str(candidate),
                    manifest=manifest,
                    checksums={str(key): str(value) for key, value in expected.items()},
                )
            )
    if len(matches) != 1:
        raise MatrixExecutionError(
            f"cannot safely resume run {run_id}: expected exactly one checksum-valid matching scientific result, found {len(matches)}"
        )
    return matches[0]


def _matrix_fingerprint_payload(
    *,
    package_id: str,
    package_fingerprint: str,
    plan_hash: str,
    run_ids: tuple[str, ...],
    mesh_configuration_hash: str,
) -> dict[str, object]:
    return {
        "schema_version": MATRIX_EXECUTION_SCHEMA_VERSION,
        "package_id": package_id,
        "package_fingerprint": package_fingerprint,
        "plan_hash": plan_hash,
        "run_ids": list(run_ids),
        "mesh_configuration_hash": mesh_configuration_hash,
        "sequential_execution": True,
        "max_concurrent_solver_jobs": 1,
        "randomized_plan_order_preserved": True,
        "biological_testing": False,
        "hypothesis_analysis": False,
    }


def execute_persisted_dc_matrix(
    *,
    package_root: Path,
    rig: RigV1Schema,
    materials: MaterialLibrary,
    results_root: Path,
    mesh_config: RigGmshConfig,
    created_utc: datetime | None = None,
    executables: ExecutableSet | None = None,
    single_run_executor=execute_and_persist_single_run,
) -> PersistedDcMatrixExecution:
    """Execute one immutable DC plan strictly in its persisted randomized order.

    This is orchestration, not a parallel/batch FEM solve. Every member remains a separately
    checksummed scientific single-run execution. At most one solver job is active at a time. If an
    earlier compatible result exists, it is reused only after its complete checksum set and manifest
    identity are verified; this makes interrupted matrices resumable without overwriting evidence.
    """
    package, _, matrix = _validate_package_identity(package_root)
    run_ids = package.run_ids
    mesh_hash = mesh_config.configuration_hash()
    matrix_fingerprint = _canonical_sha256(
        _matrix_fingerprint_payload(
            package_id=package.package_id,
            package_fingerprint=package.package_fingerprint,
            plan_hash=package.plan_hash,
            run_ids=run_ids,
            mesh_configuration_hash=mesh_hash,
        )
    )
    matrix_execution_id = f"matrix-{matrix_fingerprint[:16]}"
    final_root = (
        results_root
        / package.experiment_id
        / "matrix_executions"
        / package.package_id
        / matrix_execution_id
    )
    if final_root.exists():
        raise FileExistsError(f"DC matrix execution already exists: {matrix_execution_id}")
    final_root.parent.mkdir(parents=True, exist_ok=True)
    staging_root = final_root.parent / f".{matrix_execution_id}.staging-{uuid4().hex}"
    started = created_utc or datetime.now(timezone.utc)
    if started.tzinfo is None or started.utcoffset() != timezone.utc.utcoffset(started):
        raise ValueError("created_utc must be timezone-aware UTC")

    row_by_run_id = {str(row["run_id"]): row for row in matrix}
    records: list[DcMatrixRunRecord] = []
    staging_root.mkdir(parents=True, exist_ok=False)
    try:
        for sequence_index, run_id in enumerate(run_ids):
            row = row_by_run_id[run_id]
            reused = False
            try:
                result = single_run_executor(
                    package_root=package_root,
                    run_id=run_id,
                    rig=rig,
                    materials=materials,
                    results_root=results_root,
                    mesh_config=mesh_config,
                    executables=executables,
                )
            except FileExistsError:
                result = _verify_existing_single_run(
                    scientific_root=(
                        results_root
                        / package.experiment_id
                        / "executions"
                        / package.package_id
                        / run_id
                        / "scientific"
                    ),
                    package_id=package.package_id,
                    run_id=run_id,
                    mesh_configuration_hash=mesh_hash,
                )
                reused = True

            relative = str(Path(result.root).relative_to(results_root))
            records.append(
                DcMatrixRunRecord(
                    sequence_index=sequence_index,
                    run_id=run_id,
                    state_id=str(row["state_id"]),
                    job_id=result.manifest.job_id,
                    job_fingerprint=result.manifest.job_fingerprint,
                    solver_route=result.manifest.solver_route,
                    solver_execution=result.manifest.solver_execution,
                    reused_verified_result=reused,
                    relative_result_path=relative,
                )
            )
            _write_json(
                staging_root / "progress.json",
                {
                    "matrix_execution_id": matrix_execution_id,
                    "package_id": package.package_id,
                    "plan_hash": package.plan_hash,
                    "completed_run_count": len(records),
                    "run_count": len(run_ids),
                    "runs": [record.model_dump(mode="json") for record in records],
                },
            )

        completed = datetime.now(timezone.utc)
        manifest = DcMatrixExecutionManifest(
            matrix_execution_id=matrix_execution_id,
            matrix_fingerprint=matrix_fingerprint,
            experiment_id=package.experiment_id,
            package_id=package.package_id,
            package_fingerprint=package.package_fingerprint,
            plan_hash=package.plan_hash,
            mesh_configuration_hash=mesh_hash,
            created_utc=started,
            completed_utc=completed,
            run_count=len(run_ids),
            completed_run_count=len(records),
            runs=tuple(records),
        )
        _write_json(staging_root / "matrix_manifest.json", manifest.model_dump(mode="json"))
        checksums = _collect_checksums(staging_root)
        _write_json(staging_root / "checksums.json", checksums)
        staging_root.rename(final_root)
    except Exception as exc:
        failed_root = final_root.parent / f"{matrix_execution_id}-failed-{uuid4().hex[:8]}"
        _write_json(
            staging_root / "failure.json",
            {
                "matrix_execution_id": matrix_execution_id,
                "package_id": package.package_id,
                "completed_run_count": len(records),
                "run_count": len(run_ids),
                "error_type": type(exc).__name__,
                "error": str(exc),
                "runs": [record.model_dump(mode="json") for record in records],
            },
        )
        staging_root.rename(failed_root)
        raise MatrixExecutionError(
            f"DC matrix execution stopped after {len(records)} of {len(run_ids)} runs: {exc}",
            evidence_root=str(failed_root),
        ) from exc

    return PersistedDcMatrixExecution(root=str(final_root), manifest=manifest, checksums=checksums)
