import pytest

from pvl.orchestrator.jobs import JobState, job_from_preflight, transition_job
from pvl.orchestrator.preflight import PreflightReport, SolverRoute


def _report(ready: bool):
    return PreflightReport(
        ready=ready,
        solver_route=SolverRoute.MAGNETOSTATIC,
        issues=(),
        actual_rig_fingerprint="a" * 64,
        actual_material_fingerprint="b" * 64,
    )


def test_ready_preflight_creates_ready_job():
    job = job_from_preflight(
        job_id="job-1",
        configuration_hash="c" * 64,
        physics_state_hash="d" * 64,
        result_root="results/job-1",
        preflight=_report(True),
    )
    assert job.state == JobState.READY
    assert transition_job(job, JobState.RUNNING).state == JobState.RUNNING


def test_failed_preflight_cannot_create_ready_job():
    with pytest.raises(ValueError):
        job_from_preflight(
            job_id="job-2",
            configuration_hash="c" * 64,
            physics_state_hash="d" * 64,
            result_root="results/job-2",
            preflight=_report(False),
        )


def test_completed_job_is_terminal():
    job = job_from_preflight(
        job_id="job-3",
        configuration_hash="c" * 64,
        physics_state_hash="d" * 64,
        result_root="results/job-3",
        preflight=_report(True),
    )
    running = transition_job(job, JobState.RUNNING)
    completed = transition_job(running, JobState.COMPLETED)
    with pytest.raises(ValueError):
        transition_job(completed, JobState.RUNNING)
