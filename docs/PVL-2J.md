# PVL-2J — Controlled Rig Configuration Editor

Status: implementation candidate

## Objective

Extend the controlled Rig manifest editor so non-geometric experiment configuration can be declared without exposing solver execution.

## Added controls

- Versioned backend material catalog via `GET /api/v1/materials`.
- Ambient medium selection.
- Frame material selection.
- Copper-boundary material selection.
- Sample-vessel wall material selection.
- Sample chamber medium selection: air, distilled water, or 0.9% saline where available in the material library.
- Coil A and Coil B conductor material selection.
- Copper boundary baseline open/closed state.
- Copper-to-frame electrical-isolation state.

The browser never invents a material record. Choices come from the active Python material library and display model/provenance metadata and solver warnings.

## Scientific boundary

PVL-2J changes manifest configuration only. It does not start Gmsh/GetDP, modify FEM equations, change validation tolerances, or invoke the Portal Hypothesis Analyzer.

The 0.9% saline entry remains a controlled comparison medium, not a text-confirmed requirement. The documented Rig v1 baseline remains an electrically isolated copper boundary with a deliberate gap unless a closed-loop case is explicitly selected.

## Validation

CI must pass:

- Python/API tests including material-catalog coverage.
- Frontend TypeScript typecheck.
- Frontend production build.
- Existing POC-001 through POC-005 FEM regression chain.

## Next unit

PVL-2K should introduce a controlled electromagnetic excitation-state editor for Coil A/Coil B (off/on, current, polarity, and later-safe frequency/phase fields) while retaining the rule that editing an experiment configuration is separate from executing a solver job.
