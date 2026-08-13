from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from pvl.orchestrator.preflight import PreflightReport, SolverRoute


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
