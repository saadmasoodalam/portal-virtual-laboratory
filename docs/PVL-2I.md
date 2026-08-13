# PVL-2I — Controlled Rig Manifest Editor

Status: implementation candidate

## Objective

Provide the first controlled browser workflow for entering Rig v1 dimensions and measurement provenance without exposing FEM or solver execution.

## Implemented scope

- `GET /api/v1/rig/template` returns the canonical empty `RigV1Schema` from the backend. It contains no invented dimensions: required measurements begin as `status = unknown` with null values.
- The React client can create a new Rig manifest from that canonical template or load an existing Rig JSON file.
- Measurement records are discovered from the manifest structure rather than duplicated as a second hard-coded geometry schema in the browser.
- Every editable measurement exposes its SI value, provenance status, source note, and required/optional state.
- Supported provenance states remain exactly those defined by the backend: `unknown`, `illustrative`, `measured`, and `supplier`.
- Unknown measurements cannot be given a value through the editor. Changing a field back to `unknown` clears its value.
- The preview button remains disabled while any solver-required measurement is unknown or lacks a value.
- A completed manifest is still sent through `POST /api/v1/rig/preview`; the browser never promotes its own local completeness check to scientific authority.
- Manifests can be exported as JSON for inspection and reproducibility.

## Fidelity rules

`illustrative` means the value is suitable only for computational/visual exploration. It does not represent the physical Rig.

`measured` and `supplier` are the only hardware-fidelity provenance classes currently recognized by the backend readiness model. Source notes are retained so the physical origin of a value can be recorded.

The editor does not invent dimensions, infer missing measurements, silently convert illustrative values to measured values, or alter material physics.

## Scientific boundary

PVL-2I remains upstream of the solver stack. It cannot execute Gmsh, GetDP, POC jobs, parameter sweeps, thermal models, or the Portal Hypothesis Analyzer. The existing preview endpoint remains `solver_execution = false`.

## Validation gate

- Python/API regression tests include the new canonical template endpoint and verify that default measurements are unknown with null values.
- Frontend TypeScript typecheck and production build must pass.
- Existing POC-001 through POC-005 FEM regressions remain unchanged and must pass before merge.

## Next unit

PVL-2J should add controlled non-dimensional Rig configuration editing (material selections, chamber medium, copper open/closed state, and other safe manifest-level switches) using backend-authoritative option data. Solver execution should remain disabled until the full manifest and hardware-fidelity gates are deliberately connected to a later simulation-job API.
