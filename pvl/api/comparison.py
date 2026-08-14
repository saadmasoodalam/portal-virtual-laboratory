from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from pvl.analysis.comparison import (
    PhysicsComparisonRequest,
    PhysicsComparisonResult,
    PhysicsSample,
    compare_physics_series,
)
from pvl.api.results import read_verified_scientific_run
from pvl.orchestrator.execution import PackageIntegrityError


class TrustedRunReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    package_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    run_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    job_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    state_id: str
    repetition_index: int = Field(ge=0)
    parameter_value: float


class TrustedPhysicsComparisonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    comparison_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    experiment_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    parameter_name: str
    metric_name: str
    runs: tuple[TrustedRunReference, ...]
    control_state_id: str | None = None
    temperature_metric_name: str | None = None
    minimum_repetitions: int = Field(default=3, ge=2)
    max_relative_std: float = Field(default=0.05, gt=0.0)
    transition_robust_z: float = Field(default=5.0, gt=0.0)
    thermal_abs_correlation_threshold: float = Field(default=0.90, gt=0.0, le=1.0)


def build_comparison_router(*, results_root: Path) -> APIRouter:
    router = APIRouter(prefix="/api/v1/comparisons", tags=["comparisons"])

    @router.post("/physics", response_model=PhysicsComparisonResult)
    def physics_comparison(request: TrustedPhysicsComparisonRequest) -> PhysicsComparisonResult:
        samples: list[PhysicsSample] = []
        for reference in request.runs:
            try:
                detail = read_verified_scientific_run(
                    results_root,
                    request.experiment_id,
                    reference.package_id,
                    reference.run_id,
                    reference.job_id,
                )
            except FileNotFoundError as exc:
                raise HTTPException(
                    status_code=404,
                    detail={"code": "scientific_result_not_found", "message": str(exc)},
                ) from exc
            except PackageIntegrityError as exc:
                raise HTTPException(
                    status_code=409,
                    detail={"code": "scientific_result_integrity_failed", "message": str(exc)},
                ) from exc

            configuration_hash = detail.experiment_metadata.get("configuration_hash")
            if not isinstance(configuration_hash, str) or len(configuration_hash) != 64:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "scientific_result_identity_incomplete",
                        "message": f"verified run lacks configuration hash: {reference.job_id}",
                    },
                )
            samples.append(
                PhysicsSample(
                    run_id=reference.run_id,
                    state_id=reference.state_id,
                    repetition_index=reference.repetition_index,
                    parameter_value=reference.parameter_value,
                    metrics=detail.metrics,
                    mesh_configuration_hash=detail.summary.mesh_configuration_hash,
                    configuration_hash=configuration_hash,
                    solver_execution=detail.summary.solver_execution,
                    checksum_verified=detail.summary.checksum_verified,
                    physical_validation=detail.summary.physical_validation,
                    hypothesis_analysis=detail.summary.hypothesis_analysis,
                )
            )

        try:
            comparison_request = PhysicsComparisonRequest(
                comparison_id=request.comparison_id,
                parameter_name=request.parameter_name,
                metric_name=request.metric_name,
                samples=tuple(samples),
                control_state_id=request.control_state_id,
                temperature_metric_name=request.temperature_metric_name,
                minimum_repetitions=request.minimum_repetitions,
                max_relative_std=request.max_relative_std,
                transition_robust_z=request.transition_robust_z,
                thermal_abs_correlation_threshold=request.thermal_abs_correlation_threshold,
            )
            return compare_physics_series(comparison_request)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "physics_comparison_invalid", "message": str(exc)},
            ) from exc

    return router
