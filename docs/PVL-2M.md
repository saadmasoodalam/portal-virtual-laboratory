# PVL-2M — Scientific Experiment-Plan Package Persistence

Status: implementation candidate

## Objective

Persist an already validated Rig v1 DC plan as a reproducible scientific package before any solver execution is enabled.

PVL-2M converts the in-memory PVL-2L plan into a filesystem package with explicit provenance, planned run manifests, integrity checksums, and empty raw-data locations. It does not create mesh, solver input, field, metric, or thermal results.

## Package layout

Each package is stored under:

`results/<experiment_id>/packages/<experiment_id>-<plan_hash_prefix>/`

The package contains:

- `experiment.json` — complete experiment configuration plus configuration and physics-state hashes.
- `run_matrix.json` — ordered planned runs, including state IDs, Coil A/B states, configuration hashes, and physics-state hashes.
- `package_manifest.json` — package schema version, deterministic plan hash, deterministic package fingerprint, run count, run IDs, creation timestamp, and explicit solver/biological-testing boundaries.
- `checksums.json` — SHA-256 checksums for every file present at package creation.
- `runs/<run_id>/manifest.json` — one planned run manifest for each run.
- `runs/<run_id>/raw/` — empty reserved directory for future raw solver or measurement data.

## Deterministic identity

The plan hash is derived from the canonical ordered run records. The package ID uses the experiment ID plus the first 16 hexadecimal characters of the plan hash.

The package fingerprint is derived from the package schema version, experiment configuration hash, physics-state hash, plan hash, run count, solver-execution=false, and biological-testing=false. It is independent of filesystem location and creation timestamp.

This means the same experiment configuration, DC current, repetitions, and randomization seed produce the same plan and package identity even when stored on different machines or at different times.

## Integrity and overwrite policy

Package files are written into a temporary staging directory and renamed into place only after all planned manifests and checksums are complete.

An existing package with the same deterministic identity is never overwritten. The API returns HTTP 409 instead. This prevents accidental mutation of preserved experiment evidence.

`verify_experiment_package_checksums()` verifies both individual file hashes and the expected file set.

## Solver boundary

PVL-2M creates no:

- `mesh.msh`
- `solver_input.pro`
- `solver.json`
- solver stdout/stderr logs
- `fields.vtu`
- `metrics.json`
- `summary.csv`
- `environment.json`

Those paths are declared in each planned run manifest as future artifacts, but the files do not exist until a later execution unit explicitly creates them.

The package manifest hard-codes `solver_execution=false` and `biological_testing=false`.

## API

`POST /api/v1/experiment/plan/dc/persist`

Accepts the same validated experiment configuration and positive DC current used by the PVL-2L planner. The server chooses the configured results root; the request cannot supply an arbitrary filesystem path.

The response returns package ID, plan hash, package fingerprint, configuration hash, physics-state hash, run count, relative storage path, checksum-file count, and `solver_execution=false`.

## Browser integration

After a DC matrix has been generated, the planner exposes **Persist scientific package**. The browser verifies that the returned persisted package has the same plan hash as the plan currently displayed.

## Validation gate

PVL-2M must pass:

- package-layout and persistence tests;
- checksum and tamper-detection tests;
- no-overwrite regression;
- package API tests;
- all existing Python/API tests;
- frontend typecheck and production build;
- POC-001 through POC-005 FEM regressions.

## Next unit

PVL-2N should introduce the first explicit solver-execution gate and job manifest. It should execute only a deliberately selected planned run, preserve the exact package/run fingerprints, capture solver/tool versions and environment metadata, and write raw outputs atomically. Batch execution must remain disabled until a single packaged run is proven reproducible end-to-end.
