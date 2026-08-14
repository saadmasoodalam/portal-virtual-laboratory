# PVL-2L — Controlled Rig v1 DC Run-Matrix Planner

Status: implementation candidate

## Objective

Expose the existing Rig v1 DC control-matrix planning logic through a solver-disabled API and browser panel. This unit plans reproducible experiments; it does not execute them.

## Reused planning logic

PVL-2L reuses `plan_rig_v1_dc_experiment` and the existing validated matrix functions. No second run-order algorithm is introduced.

Each repetition contains nine states: OFF/OFF, A positive, A negative, B positive, B negative, both same positive, both same negative, opposed A+/B-, and opposed A-/B+. OFF/OFF is always first. The eight active states are shuffled deterministically from the experiment randomization seed.

DC opposition uses explicit polarity. `omega_sign` remains +1 and harmonic frequency remains unset for DC states.

## API

`POST /api/v1/experiment/plan/dc` accepts an `ExperimentConfig` and a positive DC current magnitude. It returns a deterministic plan SHA-256 hash, run count, repetitions, seed, `solver_execution = false`, and ordered run records with configuration/physics hashes and Coil A/B states.

A three-repetition baseline produces 27 planned runs.

## Browser planner

The experiment editor includes a DC planning panel. It can choose current magnitude, generate the seeded matrix, inspect the ordered table, display the plan hash, and export plan JSON. The action is labeled `Plan DC matrix`; no solver job is created.

## Validation gate

CI must verify deterministic planning, 27 runs for three repetitions, OFF/OFF first in every repetition, all nine states per repetition, seed behavior, opposed polarity with DC omega sign unchanged, positive current validation, frontend build/typecheck, and the existing POC-001 through POC-005 FEM regression chain.

## Next unit

PVL-2M should formalize experiment-plan persistence and raw-data package creation around the existing `write_experiment_plan` infrastructure without adding unrestricted solver execution.
