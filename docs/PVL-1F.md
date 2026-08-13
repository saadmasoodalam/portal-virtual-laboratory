# Unit PVL-1F — Coupled Dual-Coil Conductive-Insert Benchmark

## Objective

PVL-1F combines the previously validated ordinary-physics subsystems into the first coupled time-harmonic benchmark containing two independently driven coaxial coils, relative phase control, a finite conductive insert, magnetic-field redistribution, induced response, and dissipative heating.

This is an integration benchmark, not the full Portal Boundary Physics Rig and not a Portal Hypothesis calculation.

## Dependency chain

PVL-1F retains these permanent regression gates:

- POC-001: analytical single-coil magnetic-field validation;
- POC-002: independent dual-coil superposition and cancellation;
- POC-003: harmonic phase and signed-frequency convention checks;
- POC-004: conducting-slab magnetic diffusion and skin-depth validation.

POC-005 runs only after those checks pass.

## Retained POC-005 benchmark

- coil radius: 0.05 m each;
- coil centers: z = -0.025 m and +0.025 m;
- 100 turns and 1 A peak per coil;
- 1000 Hz common frequency;
- insert inner/outer radii: 0.012 / 0.038 m;
- insert axial thickness: 0.006 m;
- insert center: z = 0;
- conductivity: 5.8e7 S/m;
- relative permeability: 1;
- skin-depth scale: approximately 2.09 mm.

The solver uses the validated axisymmetric vector-potential formulation with the harmonic conductive term. No speculative physics is inserted into the field equations.

## Validation controls

POC-005 requires three-level mesh convergence for the same-phase and pi-opposed states, zero-conductivity controls against the analytical POC-003 reference, positive dissipative loss, and independent source-superposition checks. Acceptance thresholds are fixed validation gates and are not relaxed to obtain a passing run.

The retained conductor-response sampling line is one quarter of the insert thickness away from the center plane (`z = +0.0015 m`). The exact center is not used for relative convergence because it is an antisymmetry cancellation plane in the pi-opposed state.

## Result

**COMPLETE — PASSED.** GitHub Actions run `31734467275` completed with 52 Python tests passing and POC-001 through POC-005 all passing their numerical gates using Gmsh 4.12.1 and GetDP 3.2.0.

Detailed numerical evidence and the corrected symmetry-null sampling issue are preserved in [`PVL-1F-validation.md`](PVL-1F-validation.md).

## Scientific boundary

PVL-1F validates the coupled Maxwellian/magneto-quasistatic baseline only. It does not demonstrate anomalous behavior, a portal state, or spacetime coupling.

The next stage may introduce retained Rig material families and a typed parametric Rig data model while preserving these regressions.
