# PVL-2T — Durable DC Matrix Jobs and Worker Boundary

Status: stacked implementation candidate on PVL-2S

## Objective

PVL-2T prevents a multi-run FEM matrix from being held open inside one browser HTTP request. The API queues an immutable job request and returns immediately. A separate worker process claims the job and executes the PVL-2S sequential matrix.

## Durable job record

A queued job is stored under:

```text
results/<experiment_id>/jobs/<job_id>/
├── request.json
├── request.sha256
├── claim.json                 # created by exactly one worker
└── events/
    ├── 000000-queued.json
    ├── 000001-running.json
    └── 000002-succeeded.json  # or failed
```

The request is immutable and SHA-256 protected. Status is append-only: a previous event is never rewritten to manufacture a different history.

## Queue operation

Enqueue verifies:

- immutable experiment-package checksums and package identity;
- Rig fingerprint against the packaged experiment;
- material-library fingerprint against the packaged experiment;
- explicit hashable mesh profile;
- exact persisted run ordering.

The deterministic job fingerprint includes the package, plan, run IDs, Rig, material library and mesh configuration. Re-submitting the identical job cannot silently create another execution.

Queueing performs no FEM solve.

## Worker claim

A worker opens `claim.json` with exclusive-create semantics. A second worker cannot claim the same job.

The worker then appends a `running` event and calls the PVL-2S matrix orchestrator. Solver concurrency remains one. Each matrix member remains a separate PVL-2R checksummed scientific execution.

Success appends a terminal event with the matrix result path. Failure appends a terminal failure event and references any preserved PVL-2S failure evidence.

## CLI worker

```bash
python -m pvl.cli.matrix_worker \
  --results-root results \
  --experiment-id <experiment-id> \
  --job-id <matrix-job-id>
```

The worker exits non-zero for blocked, missing, solver-error or failed matrix states.

## API

Queue:

`POST /api/v1/experiment/matrix/jobs`

```json
{
  "experiment_id": "...",
  "package_id": "...",
  "rig": {"...": "..."}
}
```

The endpoint returns HTTP 202 and a `queued` status. It does not execute Gmsh/GetDP.

Status:

`GET /api/v1/experiment/matrix/jobs/<experiment_id>/<job_id>`

The response reports the latest append-only event, whether solver execution has started, whether the job is terminal, and any matrix/failure evidence path.

## Safety and scientific boundary

The job request freezes:

- sequential execution;
- maximum one concurrent solver job;
- no biological testing;
- no Portal Hypothesis analysis.

PVL-2T is orchestration only. It does not change the FEM formulation, material equations, numerical tolerance, geometry, field output or interpretation layer.

## Crash semantics

A process-level crash after a worker claim leaves a visible `running` event and `claim.json`; it does not automatically allow a second worker to overwrite or repeat uncertain solver work. Recovery of an abandoned claim must be an explicit later operation that first audits the per-run scientific evidence.

## Dependency

PVL-2T is stacked on PVL-2S → PVL-2R → PVL-2Q. It cannot be released until the complete-Rig DC convergence gate in PVL-2Q is accepted and the stack is reconciled to main.
