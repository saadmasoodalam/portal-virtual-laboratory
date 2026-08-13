# PVL-2F — Frontend Bootstrap and Rig Preview Viewer

Status: implementation candidate

## Objective

Create the first browser client for Portal Virtual Laboratory using the PVL-2E preview-scene contract. The unit is intentionally visualization-only: it does not run FEM, alter solver input, or claim hardware-fidelity geometry.

## Implemented scope

- React + TypeScript + Vite frontend bootstrap.
- React Three Fiber / Three.js 3D viewport.
- Orbit, pan, zoom, Z-up scene convention, grid, and axes.
- Runtime parsing of exported PVL preview JSON.
- Hard guard requiring `fidelity = illustrative_geometry` and `solver_mesh = false`.
- Rendering for box envelopes, open rectangular loops, cylinders/shells, winding envelopes, and sensor points.
- Component visibility controls and click selection.
- Component/material/geometry inspector.
- Geometry fingerprint and scene metadata display.
- Responsive desktop/mobile layout.
- Separate frontend CI typecheck and production build.

## Scientific boundary

The browser consumes geometry descriptions downstream of the Rig manifest. It does not invent missing physical measurements and does not treat preview primitives as solver meshes. The rendered shapes are engineering visualization aids only.

## Inputs

PVL-2F consumes the JSON produced by the PVL-2E `PreviewScene` model. Hardware-fidelity geometry remains blocked until required Rig measurements are known and explicitly entered into the validated Rig schema.

## Dependency policy

Direct frontend dependencies are pinned to explicit versions in `frontend/package.json`. The first CI gate installs, typechecks, and builds the client independently from the Python/FEM validation job.

## Acceptance gate

1. Python/FEM regression suite remains green.
2. Frontend TypeScript typecheck passes.
3. Frontend production build succeeds.
4. Invalid/non-preview geometry cannot be silently accepted as a solver mesh.
5. No FEM equation, solver threshold, or Portal Hypothesis Analyzer behavior is modified by this unit.

## Next unit

PVL-2G should expose a narrow backend preview API so the browser can request validated Rig/preview scenes without manual JSON upload. The API must return provenance/fidelity fields and preserve the same solver-versus-preview boundary.
