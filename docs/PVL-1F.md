# Unit PVL-1F — Coupled Dual-Coil Conductive-Insert Benchmark

## Objective

Combine the independently validated PVL subsystems into the first coupled time-harmonic electromagnetic model containing:

- two independently driven coaxial coils;
- relative phase control;
- a finite conductive body;
- induced eddy current;
- magnetic shielding/redistribution;
- phase lag;
- Joule loss.

PVL-1F is deliberately **not** the full Portal Boundary Physics Rig. It is an integration benchmark whose only purpose is to prove that the previously validated ordinary-physics components still behave correctly when coupled together.

## Dependency chain

PVL-1F is downstream of the retained permanent regression baselines:

- **POC-001:** single-coil magnetostatics against an analytical field oracle;
- **POC-002:** independent dual-coil +/+ and +/- static superposition;
- **POC-003:** harmonic phase and signed-frequency conventions;
- **POC-004:** exact conducting-slab magnetic diffusion, skin depth and induced current.

The CI workflow reruns all four before the POC-005 integration gate.

## Retained POC-005 geometry

The controlled geometry uses:

- coil A radius: 0.05 m;
- coil A centre: z = -0.025 m;
- coil B radius: 0.05 m;
- coil B centre: z = +0.025 m;
- 100 turns per coil;
- 1 A peak source-current amplitude per coil;
- 2 mm × 2 mm homogenized winding sections;
- 1000 Hz common frequency magnitude;
- annular conductor inner radius: 0.012 m;
- annular conductor outer radius: 0.038 m;
- conductor axial thickness: 0.006 m;
- conductor centre: z = 0;
- retained conductivity: 5.8×10^7 S/m;
- retained relative permeability: 1.

The conductor is therefore physically separated from both coil source regions and sits symmetrically between them.

At 1000 Hz with the retained conductivity and permeability, its skin-depth scale is approximately the same 2.09 mm scale independently validated in POC-004.

## Numerical formulation

The model uses the axisymmetric vector-potential formulation already validated in POC-001/002 and adds the conductivity term independently validated in POC-004:

`curl(ν curl A) + σ ∂A/∂t = J_source`.

The solve is complex and frequency-domain. Coil source phases use GetDP's harmonic cosine phasor function. The sign of angular frequency is first mapped to the canonical positive-frequency phase representation established by POC-003; this prevents signed-frequency notation from being mistaken for a new physical rotation state in the coaxial scalar-field geometry.

The conductive insert uses a skin-depth-aware local mesh refinement. The axis probe corridor is independently refined to preserve stable field extraction.

## Measured outputs

Each numerical case preserves:

- complex axial B field at fixed probes;
- complex induced azimuthal current density across the conductor mid-plane;
- total time-averaged Joule loss in the conductive insert;
- mesh node and element counts;
- solver stdout/stderr;
- generated geometry, mesh and GetDP problem definition;
- configuration hash and solver versions.

## Validation controls

POC-005 is not accepted from one visually plausible field map. It contains several independent falsification controls.

### 1. Zero-conductivity geometry control

The insert conductivity is set to zero while its relative permeability remains 1. It must then become electromagnetically indistinguishable from air.

Both the same-phase and π-opposed-phase FEM fields are compared against the independent finite-winding POC-003 analytical phasor reference.

This control tests the combined geometry, harmonic source implementation, boundary treatment and post-processing without relying on conductor behavior.

### 2. Conductive same-phase convergence

Both coils run in phase while the conductor is active. Three successively refined meshes must stabilize:

- complex B field;
- complex induced current density;
- total Joule loss.

### 3. Conductive opposed-phase convergence

Coil B is shifted by π while the conductor is active. The same B/J/Joule convergence requirements are applied independently.

### 4. Explicit linear superposition check

At the finest retained mesh, PVL separately solves:

- coil A only;
- coil B only;
- coil A + coil B.

Because the retained materials are linear, both the complex magnetic field and complex induced current must satisfy numerical source superposition.

Joule loss is intentionally **not** required to superpose because power is quadratic in the field/current amplitude.

### 5. Positive dissipative loss

For finite positive conductivity, the time-averaged conductor Joule loss must be positive in both retained phase states.

## Initial machine gate

The automated POC-005 gate requires:

- at least 3 mesh levels for both same-phase and opposed-phase conductor states;
- strictly decreasing global mesh sizes;
- strictly increasing node and element counts;
- zero-conductivity same-phase field error below 1%;
- zero-conductivity opposed-phase field error below 1%;
- final successive complex-B change below 0.5%;
- final successive complex-J change below 1%;
- final successive Joule-loss change below 1%;
- positive final Joule loss in both phase states;
- B-field superposition error below 1×10^-5 of the expected peak field;
- induced-current superposition error below 1×10^-5 of the expected peak current.

These thresholds are validation gates, not tunable targets to be relaxed merely to obtain a green run. If a criterion fails, the geometry, formulation, mesh, source convention or extraction method must be investigated first.

## Scientific boundary

POC-005 contains no Portal Hypothesis term and no spacetime equation. Every effect in this unit is expected to be explainable through Maxwellian magneto-quasistatics and linear conductive-material response.

A successful POC-005 validates the coupled ordinary-physics baseline. It does not demonstrate anomalous behavior.

Only after this coupled baseline passes should PVL begin introducing the retained Rig material families and boundary geometry one controlled layer at a time.

## Command

```bash
pvl poc005-insert --output results/poc005_insert
```

## Unit status

**Validation branch active.** The implementation and automated gate are present; the unit remains unmerged until its full GitHub Actions evidence passes together with POC-001 through POC-004 regressions.
