# PVL-2R — Trusted Complete-Rig Scientific Single-Run Execution

Status: implementation candidate; stacked on PVL-2Q

## Objective

PVL-2R connects the immutable experiment packages and explicit single-run permission boundary from PVL-2M/PVL-2N to the complete-Rig DC magnetostatic solver introduced by PVL-2Q.

The unit does not broaden the physics model. It creates the evidence-preserving execution boundary needed to turn one already planned run into one auditable established-physics calculation.

## Execution contract

A scientific run must:

1. verify every checksum in the immutable experiment package;
2. reconstruct exactly one selected planned run;
3. verify its configuration, physics-state, Rig and material fingerprints;
4. pass the existing Rig/material/solver-route preflight;
5. compile the constructive Rig topology from the supplied Rig definition;
6. use an explicit serializable/hashable mesh configuration;
7. execute only a route that has a complete-Rig solver implementation;
8. stage all outputs under a temporary directory;
9. write normalized metadata and summaries without deleting raw solver evidence;
10. checksum the completed execution record;
11. atomically rename it into its final non-overwriting location;
12. verify the immutable source package again after execution.

## Supported routes

### OFF/OFF control

The control is persisted as a scientific run with `solver_execution=false`. No FEM solver is invoked merely to manufacture a zero result.

### DC magnetostatic

The magnetostatic route calls the actual complete-Rig Gmsh/GetDP runner from PVL-2Q. The output record has `solver_execution=true` only after the runner returns successfully.

### Harmonic / magnetoquasistatic

Still blocked. POC-004/005 validate important eddy-current primitives, but their surrogate geometry is not silently promoted to a complete-Rig harmonic solver.

## Result layout

Scientific executions are stored outside the immutable plan package:

```text
results/<experiment_id>/executions/<package_id>/<run_id>/scientific/<job_id>/
├── job_manifest.json
├── experiment.json
├── geometry.json
├── materials.json
├── solver.json
├── environment.json
├── metrics.json
├── summary.csv
├── checksums.json
└── raw/
    └── complete solver evidence
```

For a real DC solve, `raw/` receives the complete-Rig Gmsh model/mesh evidence, GetDP input, stdout/stderr, axis/probe outputs and the solver-local metrics produced by the validated runner.

No scientific result is represented only by a graph or screenshot.

## API

`POST /api/v1/experiment/execution/single/run`

The request reuses the deliberate single-run contract and requires:

```json
{
  "experiment_id": "...",
  "package_id": "...",
  "run_id": "...",
  "rig": {"...": "..."},
  "single_run_confirmation": true
}
```

The API does not accept `false` or an omitted confirmation.

## Permission gate update

The historical `/execution/single/gate` endpoint remains a permission/audit operation and still never runs Gmsh/GetDP itself. PVL-2R updates its route policy:

- control: eligible;
- complete-Rig DC magnetostatic: eligible;
- complete-Rig magnetoquasistatic: blocked pending its dedicated solver-validation unit.

`execution_allowed=true` therefore means a separate executor may proceed; it does not mean that the gate operation itself ran a solver.

## Mesh profile

PVL-2R makes the retained PVL-2Q candidate profile explicit and hashable:

- global near-Rig target: 12 mm;
- minimum mesh size: 1 mm;
- winding target: 2 mm;
- steel target: 5 mm;
- outer air margin: 100%;
- graded far-field target: 40 mm;
- fixed near-field padding fraction: 25%;
- transition thickness: 100 mm.

The profile is not described as numerically validated until PVL-2Q's independent 3% mesh/domain convergence gate passes.

## Scientific boundary

Every persisted manifest explicitly records:

- `single_run_only=true`;
- `batch_execution=false`;
- `biological_testing=false`;
- `hypothesis_analysis=false`;
- `physical_validation=false`.

A successful PVL-2R calculation is a reproducible numerical established-physics execution. It is not physical validation of the future hardware and is not evidence for a portal.

## Merge gate

PVL-2R remains draft until:

- PVL-2Q passes its retained convergence gate and merges;
- this branch is reconciled with the new main head;
- Python/API tests pass;
- frontend remains green;
- POC-001 through POC-005 remain green;
- a real complete-Rig magnetostatic execution path remains available in CI/runtime;
- no hypothesis term enters solver inputs or outputs.
