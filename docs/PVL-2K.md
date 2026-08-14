# PVL-2K — Controlled Electromagnetic Excitation-State Editor

Status: implementation candidate

## Objective

Add a separate experiment-state layer for Coil A and Coil B after the Rig manifest has been validated. Editing or validating an experiment remains distinct from executing a solver job.

## Existing model reused

PVL-2K uses the established `ExperimentConfig` and `CoilDriveState` models rather than introducing a second excitation schema.

Supported drive modes are `off`, `dc`, and `harmonic`. DC uses a positive current magnitude plus explicit polarity. Harmonic mode uses current magnitude, frequency, phase, and a signed-frequency convention. The existing Python model remains authoritative for all validation.

## API boundary

`POST /api/v1/experiment/template` creates a solver-disabled experiment draft tied to the exact Rig-definition fingerprint and active material-library fingerprint. Sample medium and copper-boundary state are derived from the Rig. Both coils begin OFF; no active current or frequency is invented.

`POST /api/v1/experiment/validate` validates the experiment model and returns its deterministic physics-state hash with `solver_execution = false`.

## Browser editor

The UI exposes Coil A and Coil B independently: drive mode, current magnitude, polarity, harmonic frequency, harmonic phase, and the `+omega/-omega` convention.

For the current coaxial electromagnetic model, signed frequency is labeled as an ordinary harmonic phase/frequency convention only. It is not interpreted as spacetime rotation or a portal effect.

Sample medium and copper-boundary state remain read-only in the experiment editor because they come from the Rig manifest. Editing the Rig invalidates the attached experiment draft so it must be regenerated after Rig validation.

## Safety and scientific boundary

- No Gmsh/GetDP execution is exposed.
- No simulation job is scheduled.
- No FEM equations or validation tolerances change.
- Biological testing remains hard-coded false.
- Portal hypotheses do not alter excitation validation.

## Validation gate

CI must pass the new experiment API tests, existing Python/API tests, frontend typecheck and production build, and POC-001 through POC-005 FEM regressions.

## Next unit

PVL-2L should add the controlled Rig v1 DC run-matrix planner using the existing `build_rig_v1_dc_baseline_states` and `randomized_repeated_dc_matrix` functions. Planning must generate reproducible run order without executing the solver.
