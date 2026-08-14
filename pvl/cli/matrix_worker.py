from __future__ import annotations

import argparse
import json
from pathlib import Path

from pvl.materials.library import load_builtin_material_library
from pvl.orchestrator.jobs import MatrixJobError, run_queued_dc_matrix_job
from pvl.orchestrator.execution import PackageIntegrityError
from pvl.solvers.getdp.runner import SolverExecutionError, SolverUnavailableError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pvl-matrix-worker")
    parser.add_argument("--results-root", default="results")
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--job-id", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        status = run_queued_dc_matrix_job(
            results_root=Path(args.results_root),
            experiment_id=args.experiment_id,
            job_id=args.job_id,
            materials=load_builtin_material_library(),
        )
    except FileNotFoundError as exc:
        print(f"PVL matrix worker: NOT FOUND — {exc}")
        return 2
    except (PackageIntegrityError, MatrixJobError) as exc:
        print(f"PVL matrix worker: BLOCKED — {exc}")
        return 3
    except (SolverUnavailableError, SolverExecutionError) as exc:
        print(f"PVL matrix worker: SOLVER ERROR — {exc}")
        return 4

    payload = {
        "job_id": status.request.job_id,
        "experiment_id": status.request.experiment_id,
        "package_id": status.request.package_id,
        "status": status.latest_event.status,
        "message": status.latest_event.message,
        "event_count": status.event_count,
        "matrix_result_path": status.latest_event.matrix_result_path,
        "failure_evidence_path": status.latest_event.failure_evidence_path,
    }
    print(json.dumps(payload, indent=2))
    return 0 if status.latest_event.status == "succeeded" else 9


if __name__ == "__main__":
    raise SystemExit(main())
