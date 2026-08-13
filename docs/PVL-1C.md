# Unit PVL-1C — Independent Dual-Coil Magnetostatic Baseline

## Objective

Extend the validated PVL-1B single-coil numerical stack into two independently controlled coaxial field systems and prove that ordinary linear superposition, polarity reversal, field parity and mid-plane cancellation behave correctly before introducing frequency, phase, conductive materials, water or any Portal Hypothesis terms.

## Implemented in this unit

- independent coil A and coil B configuration;
- independent current magnitude and polarity for each coil;
- deterministic configuration hashing including both coil states;
- analytical two-filament superposition oracle;
- independent finite winding-section superposition oracle;
- zero-safe field-comparison metrics for configurations containing analytical zero crossings;
- conformal two-source axisymmetric Gmsh geometry;
- two-source GetDP magnetostatic formulation;
- hierarchical second-order magnetic solution with linear geometric elements;
- same-polarity (+/+) convergence sequence;
- opposed-polarity (+/-) convergence sequence;
- even-symmetry diagnostic for +/+;
- odd-antisymmetry diagnostic for +/-;
- explicit mid-plane cancellation diagnostic for +/-;
- automated POC-002 acceptance gate;
- CI evidence artifacts.

## Deliberate physics boundary

PVL-1C remains entirely inside established static electromagnetics. It does not introduce oscillation frequency, +ω/-ω, phase, eddy currents, Joule heating, iron, copper bulk conductors, water/saline dielectric behavior, thermal coupling, or any Portal Hypothesis equation.

This separation is intentional. The two field systems must first behave correctly under ordinary magnetostatic superposition before dynamic or material coupling is added.

## Retained geometry

Default PVL-POC-002 configuration:

- coil A radius: 0.05 m;
- coil A turns: 100;
- coil A current: 1 A;
- coil A centre: z = -0.025 m;
- coil B radius: 0.05 m;
- coil B turns: 100;
- coil B current: 1 A;
- coil B centre: z = +0.025 m;
- source section for each winding: 0.002 m × 0.002 m;
- same-polarity state: A=+1, B=+1;
- opposed-polarity state: A=+1, B=-1;
- probe positions: -0.10, -0.05, -0.025, 0, +0.025, +0.05, +0.10 m;
- second-order magnetic solution space;
- mesh sequence: 0.03, 0.02 and 0.012 m with scaled local refinement.

## Why POC-002 uses peak-normalized error

The opposed-polarity state has a physically required zero field at the exact mid-plane. Ordinary pointwise relative error is undefined when the analytical reference is zero. POC-002 therefore normalizes absolute field error to the peak magnitude of the analytical field across the retained probe set.

This allows the same metric to evaluate non-zero regions and exact cancellation regions without hiding the zero crossing or adding an artificial denominator.

## CI validation evidence

GitHub Actions executed both polarity states through three mesh levels. The finest mesh contained 39,459 nodes and 79,421 elements for each state.

### Same-polarity (+/+) state

Finest-mesh results:

- analytical finite-source peak field: approximately 0.001798305 T;
- FEM centre field: approximately 0.001797113 T;
- maximum peak-normalized absolute error: approximately 0.0701%;
- RMS peak-normalized error: approximately 0.0669%;
- final successive field change: approximately 0.000772%;
- even-symmetry mismatch: approximately 0.0000426%.

The field is therefore additive and even about the mid-plane to substantially tighter accuracy than the acceptance thresholds.

### Opposed-polarity (+/-) state

Finest-mesh results:

- analytical finite-source peak magnitude: approximately 0.000812250 T;
- maximum peak-normalized absolute error: approximately 0.01525%;
- RMS peak-normalized error: approximately 0.00824%;
- final successive field change: approximately 0.00296%;
- odd-antisymmetry mismatch: approximately 0.0000862%;
- FEM mid-plane residual: approximately -2.67×10^-10 T;
- mid-plane residual normalized to analytical peak: approximately 0.0000329%.

The opposed state therefore reproduces the expected sign reversal, odd field parity and near-zero mid-plane cancellation without any special numerical correction.

## Automated POC-002 gate

`pvl poc002-fem` runs both +/+ and +/- convergence sequences and returns non-zero unless every retained criterion passes:

- at least 3 mesh levels for each state;
- strictly decreasing mesh sizes;
- strictly increasing node and element counts;
- finest maximum peak-normalized field error below 1% in each state;
- finest RMS peak-normalized error below 0.5% in each state;
- final successive peak-normalized field change below 0.1% in each state;
- +/+ even-symmetry error below 0.01%;
- +/- odd-antisymmetry error below 0.01%;
- +/- centre-cancellation residual below 0.1% of the analytical peak field.

The retained CI evidence passes every gate criterion.

## Scientific meaning

PVL now has validated numerical evidence that two independently controlled coaxial field sources reproduce ordinary superposition and polarity reversal at the required accuracy. This is a prerequisite for later experiments involving phase and direction controls.

The result does **not** demonstrate a portal, spacetime coupling, anomalous energy, or any departure from Maxwellian magnetostatics. It establishes the ordinary-physics baseline against which later dynamic and material-coupled simulations can be tested.

## Command

```bash
pvl poc002-fem --output results/poc002_fem
```

## Unit status

PVL-1C / POC-002: **validated in CI** for retained +/+ and +/- static field states.

The next controlled expansion may introduce time dependence and phase only while preserving these magnetostatic states as regression baselines.
