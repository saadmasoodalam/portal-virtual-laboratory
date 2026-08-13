# PVL-2G — Validated Rig Preview API

Status: implementation candidate

## Objective

Expose the PVL-2E geometry preview pipeline through a narrow FastAPI boundary so a browser client can request a validated Rig scene without invoking a solver.

## API surface

- `GET /api/v1/health` reports the preview-only API scope and explicitly reports solver execution as disabled.
- `POST /api/v1/rig/preview` accepts a `RigV1Schema` document and returns the validated illustrative preview scene.

## Scientific boundary

PVL-2G does not execute Gmsh, GetDP, a simulation job, or the Portal Hypothesis Analyzer. The endpoint calls the existing geometry adapter and therefore refuses a Rig whose required geometry measurements are unknown or whose material references are invalid.

Successful responses preserve:

- Rig readiness state.
- Geometry fingerprint.
- `fidelity = illustrative_geometry`.
- `solver_mesh = false`.
- Material-library version and SHA-256 fingerprint.

Hardware-fidelity constructive geometry remains unavailable until measured/supplier Rig dimensions and materials satisfy the existing readiness gates and a constructive adapter is implemented.

## Failure behavior

A structurally valid but computationally incomplete Rig receives HTTP 422 with explicit readiness reasons. Pydantic/FastAPI validation remains responsible for malformed request payloads.

## Test gate

The unit adds API tests for health scope, rejection of an incomplete Rig, deterministic preview generation, fidelity labeling, and material/geometry provenance. Existing FEM validation remains unchanged and continues to run in CI.

## Next unit

PVL-2H should connect the React viewer to this endpoint while retaining local JSON import as a diagnostic fallback. It should not expose solver execution yet.
