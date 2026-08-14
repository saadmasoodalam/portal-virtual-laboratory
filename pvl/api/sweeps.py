from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from pvl.experiments.models import ExperimentConfig
from pvl.materials.library import MaterialLibrary
from pvl.rig.schema import RigV1Schema
from pvl.sweeps.dc import DcSweepDefinition, plan_dc_sweep
from pvl.sweeps.package import persist_dc_sweep_plan


class DcSweepPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    definition: DcSweepDefinition
    rig: RigV1Schema
    experiment: ExperimentConfig
    persist: bool = False


class DcSweepPlanResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    sweep_id: str
    sweep_hash: str
    point_count: int
    coil_a_value_count: int
    coil_b_value_count: int
    medium_count: int
    copper_state_count: int
    solver_execution: bool = False
    hypothesis_analysis: bool = False
    persisted: bool = False
    relative_path: str | None = None
    point_ids: tuple[str, ...]
    point_hashes: tuple[str, ...]


def build_sweeps_router(*, materials: MaterialLibrary, results_root: Path) -> APIRouter:
    router = APIRouter(prefix="/api/v1/sweeps", tags=["sweeps"])

    @router.post("/dc/plan", response_model=DcSweepPlanResponse)
    def plan_dc(request: DcSweepPlanRequest) -> DcSweepPlanResponse:
        try:
            plan = plan_dc_sweep(
                request.definition,
                base_rig=request.rig,
                base_experiment=request.experiment,
                materials=materials,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "dc_sweep_invalid", "message": str(exc)},
            ) from exc

        relative_path: str | None = None
        if request.persist:
            try:
                persisted = persist_dc_sweep_plan(plan, results_root)
            except FileExistsError as exc:
                raise HTTPException(
                    status_code=409,
                    detail={"code": "dc_sweep_exists", "message": str(exc)},
                ) from exc
            relative_path = str(persisted.root.relative_to(results_root))

        return DcSweepPlanResponse(
            sweep_id=plan.sweep_id,
            sweep_hash=plan.sweep_hash,
            point_count=plan.point_count,
            coil_a_value_count=len(request.definition.coil_a_current_a.values()),
            coil_b_value_count=len(request.definition.coil_b_current_a.values()),
            medium_count=len(request.definition.media),
            copper_state_count=len(request.definition.copper_boundary_states),
            persisted=request.persist,
            relative_path=relative_path,
            point_ids=tuple(point.point_id for point in plan.points),
            point_hashes=tuple(point.point_hash for point in plan.points),
        )

    return router
