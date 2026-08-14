from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from pvl.materials.library import MaterialLibrary
from pvl.orchestrator.execution import PackageIntegrityError
from pvl.orchestrator.jobs import MatrixJobStatus, enqueue_dc_matrix_job, load_matrix_job_status
from pvl.orchestrator.scientific_execution import exploratory_complete_rig_dc_mesh_profile
from pvl.rig.schema import RigV1Schema


class MatrixJobCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    experiment_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    package_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    rig: RigV1Schema


class MatrixJobStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    job_id: str
    job_fingerprint: str
    experiment_id: str
    package_id: str
    run_count: int
    status: str
    message: str
    event_count: int
    solver_execution_started: bool
    terminal: bool
    matrix_result_path: str | None = None
    failure_evidence_path: str | None = None
    max_concurrent_solver_jobs: int
    biological_testing: bool
    hypothesis_analysis: bool


def _response(status: MatrixJobStatus) -> MatrixJobStatusResponse:
    event = status.latest_event
    return MatrixJobStatusResponse(
        job_id=status.request.job_id,
        job_fingerprint=status.request.job_fingerprint,
        experiment_id=status.request.experiment_id,
        package_id=status.request.package_id,
        run_count=status.request.run_count,
        status=event.status,
        message=event.message,
        event_count=status.event_count,
        solver_execution_started=event.status in {"running", "succeeded", "failed"},
        terminal=event.status in {"succeeded", "failed"},
        matrix_result_path=event.matrix_result_path,
        failure_evidence_path=event.failure_evidence_path,
        max_concurrent_solver_jobs=status.request.max_concurrent_solver_jobs,
        biological_testing=status.request.biological_testing,
        hypothesis_analysis=status.request.hypothesis_analysis,
    )


def build_matrix_jobs_router(*, materials: MaterialLibrary, results_root: Path) -> APIRouter:
    router = APIRouter(prefix="/api/v1/experiment/matrix/jobs", tags=["matrix-jobs"])

    @router.post("", response_model=MatrixJobStatusResponse, status_code=202)
    def create_matrix_job(request: MatrixJobCreateRequest) -> MatrixJobStatusResponse:
        package_root = results_root / request.experiment_id / "packages" / request.package_id
        try:
            status = enqueue_dc_matrix_job(
                package_root=package_root,
                rig=request.rig,
                materials=materials,
                results_root=results_root,
                mesh_config=exploratory_complete_rig_dc_mesh_profile(),
            )
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail={"code": "experiment_package_not_found", "message": str(exc)},
            ) from exc
        except PackageIntegrityError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "matrix_job_integrity_failed", "message": str(exc)},
            ) from exc
        except FileExistsError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "matrix_job_exists", "message": str(exc)},
            ) from exc
        return _response(status)

    @router.get("/{experiment_id}/{job_id}", response_model=MatrixJobStatusResponse)
    def matrix_job_status(experiment_id: str, job_id: str) -> MatrixJobStatusResponse:
        try:
            status = load_matrix_job_status(
                results_root=results_root,
                experiment_id=experiment_id,
                job_id=job_id,
            )
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail={"code": "matrix_job_not_found", "message": str(exc)},
            ) from exc
        except PackageIntegrityError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "matrix_job_integrity_failed", "message": str(exc)},
            ) from exc
        return _response(status)

    return router
