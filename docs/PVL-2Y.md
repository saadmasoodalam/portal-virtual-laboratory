# PVL-2Y — Physics-First Comparison and Transition Gate

Status: stacked implementation candidate on PVL-2X

## Objective

PVL-2Y analyzes trusted scientific results before any project-specific interpretation is allowed. Its job is to calculate ordinary numerical differences, repeatability, derivatives, control subtraction and obvious artifact correlations while retaining an explicit prohibition on Portal classification.

## Input integrity

The API comparison path accepts run references, not user-supplied scalar values. PVL reloads each referenced scientific run through the checksum-verifying result catalog and builds the analysis samples from those verified metrics and signed identities.

A checksum failure blocks the comparison.

## Repeatability first

Samples are grouped by physical state and parameter value. For every group PVL calculates:

- repetition count;
- mean;
- sample standard deviation;
- relative standard deviation;
- standard error;
- mesh-identity count;
- optional control-subtracted mean.

A state passes the first repeatability gate only when it contains the configured minimum number of repetitions and its relative variation is below the configured limit.

## Adjacent finite differences

Within each state family, sorted adjacent parameter values produce:

`Delta M = M_(i+1) - M_i`

and

`dM/dx ~= Delta M / Delta x`.

PVL calculates a robust derivative score using the median and median absolute deviation where possible. A derivative outlier becomes a **transition candidate** only if both adjacent states also pass repeatability and mesh-identity gates.

A transition candidate is not an anomaly claim. It is a target for more ordinary-physics investigation.

## Thermal artifact check

When a temperature metric is supplied, PVL calculates the Pearson correlation between the selected observable and temperature. Strong absolute correlation above the configured threshold is explicitly flagged as a thermal explanation requiring control before interpretation.

## Control subtraction

If a control state is specified, its mean is calculated explicitly and each state summary receives a control-subtracted mean. Subtraction never removes the underlying raw values or authorizes a hypothesis classification.

## Hard interpretation boundary

Every PhysicsComparisonResult contains:

- `unexplained_residual_claim_allowed=false`;
- `portal_interpretation_allowed=false`.

These fields are constants in the established-physics engine. The comparison engine cannot promote its own transition candidate into a Portal state.

## API

`POST /api/v1/comparisons/physics`

The request identifies trusted persisted runs and maps each to its experimental state/repetition/parameter coordinate. PVL resolves the metrics server-side from checksum-verified evidence.

## Next action policy

PVL emits one physics-oriented next action:

- repeat failed states;
- resolve mesh inconsistency;
- investigate thermal correlation;
- investigate derivative candidates with mesh/tolerance/material/control studies;
- or record that no abrupt transition survived the current gate.

The downstream hypothesis analyzer may only be considered after a later evidence-review layer explicitly documents that ordinary explanations have been exhausted.
