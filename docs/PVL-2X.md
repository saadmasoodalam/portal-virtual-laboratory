# PVL-2X — Deterministic Multi-State DC Sweep Planning

Status: stacked implementation candidate on PVL-2W

## Objective

PVL-2X turns the parameter-sweep requirement from PVL-1A into a deterministic, auditable planning system. It does **not** execute thousands of FEM jobs merely because a parameter grid can be described.

## Sweep axes

The first planner supports Cartesian combinations of:

- signed Coil A DC current;
- signed Coil B DC current;
- sample medium: air / distilled water / 0.9% saline comparison;
- copper boundary: open / closed.

The architecture example `-2 A ... +2 A` in 0.25 A steps yields 17 states per coil:

- 17 × 17 × 3 media = **867** points;
- open + closed copper doubles the plan to **1,734** points.

A configurable cardinality gate rejects unexpectedly large plans before any solver work begins.

## Constructive-state integrity

Medium and copper state are not stored merely as labels. Each sweep point receives a complete Rig snapshot with:

- `sample_chamber.medium_material_id` changed to the selected medium;
- `copper_boundary.baseline_open_loop` changed to the selected topology;
- a new Rig fingerprint;
- a matching ExperimentConfig and configuration/physics hashes.

Every generated point is passed through the ordinary PVL scientific preflight. This prevents one mesh from being falsely labeled as a different sample medium or open/closed topology.

## Signed current

Signed current is mapped to established excitation state only:

- `0` -> coil OFF;
- positive -> DC magnitude with polarity `+1`;
- negative -> DC magnitude with polarity `-1`.

This is an electrical convention. No spacetime or project spiral interpretation is introduced.

## Determinism

Sweep ranges are generated from decimal representations to avoid cumulative binary floating-point stepping drift. Point order is fixed as:

`Coil A -> Coil B -> medium -> copper state`

Each point receives a SHA-256 identity from its physical state and hashes. The complete sweep receives a SHA-256 identity over its definition and ordered point hashes.

Identical inputs therefore produce identical point ordering, point hashes and sweep hash.

## Immutable persistence

A planned sweep may be stored atomically under:

```text
results/<sweep_id>/sweeps/<sweep_hash>/
├── plan.json
├── manifest.json
└── checksums.json
```

The package preserves the complete Rig and Experiment snapshots for every point. It contains no mesh, solver input or FEM result.

## API

`POST /api/v1/sweeps/dc/plan`

The request contains the definition, base Rig, base experiment and an optional `persist` flag. The response returns the sweep identity, cardinality, axis counts and ordered point IDs/hashes while explicitly reporting:

- `solver_execution=false`;
- `hypothesis_analysis=false`.

## Scientific boundary

PVL-2X is experiment-space generation only. It does not decide which point is unusual, does not tune parameters toward a desired effect, and does not classify any Portal state.

The next comparison stage must analyze completed trusted results using ordinary numerical/statistical controls before any hypothesis-specific layer is allowed to consume them.
