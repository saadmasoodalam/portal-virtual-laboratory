# PVL-2S — Resumable Sequential DC Matrix Execution

Status: stacked implementation candidate on PVL-2R

## Objective

PVL-2S turns an immutable, randomized DC experiment package into a controlled sequence of separately auditable scientific executions. It does not create a new solver and it does not bypass the single-run evidence boundary established by PVL-2R.

## Execution model

The persisted package remains authoritative for run order. PVL executes exactly that sequence:

1. verify the immutable package and plan hash;
2. read the persisted randomized run IDs in order;
3. execute one run through PVL-2R;
4. persist that run's independent checksummed scientific evidence;
5. update matrix progress;
6. proceed to the next run only after the previous run has returned;
7. write a final checksummed matrix manifest only after every planned run is accounted for.

The matrix orchestrator therefore records:

- `sequential_execution=true`;
- `max_concurrent_solver_jobs=1`;
- `randomized_plan_order_preserved=true`;
- `biological_testing=false`;
- `hypothesis_analysis=false`;
- `physical_validation=false`.

A matrix is orchestration of single-run jobs, not a parallel FEM batch shortcut.

## Resume policy

Interrupted work must not overwrite a completed scientific result. If a selected single-run identity already exists, PVL reuses it only when exactly one candidate:

- has a valid scientific-run manifest;
- has a complete checksum set matching its files;
- belongs to the expected package and run ID;
- uses the expected mesh-configuration hash.

Zero or multiple matching candidates are treated as an unsafe resume condition and stop the matrix.

## Failure evidence

The in-progress matrix writes `progress.json` after each completed run. If a later solve fails, PVL preserves a separate failed-matrix evidence directory containing:

- the completed run records;
- total planned run count;
- exception type and message;
- the last persisted progress file.

The failure is surfaced to the caller instead of being converted into a successful or partially complete matrix.

## Final result layout

```text
results/<experiment_id>/matrix_executions/<package_id>/<matrix_id>/
├── matrix_manifest.json
├── progress.json
└── checksums.json
```

The matrix manifest references the separately persisted per-run scientific evidence rather than duplicating or rewriting it.

## Scientific boundary

PVL-2S changes orchestration only. It does not alter Gmsh geometry, GetDP equations, material properties, validation tolerances, solver outputs, or hypothesis classification.

OFF/OFF remains a non-solver control. Active DC states use the complete-Rig magnetostatic route. Harmonic states remain unavailable until a complete-Rig magnetoquasistatic solver passes its own validation gate.

## Dependency and merge gate

PVL-2S is stacked on PVL-2R, which is stacked on PVL-2Q. It remains a candidate until:

- PVL-2Q passes complete-Rig numerical convergence;
- PVL-2R is reconciled with that validated solver and passes CI;
- matrix ordering, failure preservation, resume safety and no-overwrite tests pass;
- regression POCs remain green;
- the matrix is exposed through a durable job/status API rather than a long blocking browser request.
