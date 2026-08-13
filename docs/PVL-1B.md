# Unit PVL-1B — Solver Stack Proof of Concept and Repository Bootstrap

## Objective

Create the executable Python foundation for PVL and establish the first numerical validation problem before implementing the full Portal Boundary Physics Rig v1.

## Implemented in this unit

- installable Python 3.12+ package and CLI;
- immutable, validated experiment configuration;
- deterministic canonical JSON and SHA-256 configuration hashing;
- textbook filamentary circular-coil analytical oracle;
- independent finite rectangular winding-section analytical oracle;
- parameterized 3D Gmsh geometry smoke test;
- parameterized 2D axisymmetric Gmsh FEM geometry;
- external Gmsh/GetDP executable discovery and version capture;
- GetDP axisymmetric magnetostatic formulation using established electromagnetics only;
- hierarchical second-order magnetic solution space with linear geometric elements;
- automated probe extraction, solver log preservation, mesh statistics and comparison metrics;
- multi-level mesh-convergence study;
- explicit automated numerical acceptance gate;
- GitHub Actions CI and downloadable evidence artifacts;
- unit and integration tests.

## POC-001 physics oracle

For an ideal circular N-turn coil, the analytical on-axis field is:

`B(z) = μ0 N I R² / (2 (R² + z²)^(3/2))`

The FEM model uses a finite 2 mm × 2 mm homogenized winding section at a 50 mm mean radius. PVL therefore also integrates the exact circular-loop expression over the finite winding section with Gauss-Legendre quadrature. The finite-section correction relative to the ideal filament oracle is below 0.01% for the retained probe locations, so it is independently small compared with the FEM acceptance tolerance.

## Numerical formulation correction discovered during validation

The first executable FEM version produced a field amplitude roughly 500× too large. PVL did not normalize or hide that discrepancy. Investigation isolated the axisymmetric vector-potential Jacobian/formulation as the cause. After switching to the GetDP template-compatible `VolAxiSqu` formulation, the gross scaling error disappeared.

A second issue appeared during mesh refinement: first-order field extraction was piecewise constant and produced non-monotonic point-probe behavior. PVL therefore added a hierarchical second-order GetDP magnetic solution space, systematic winding/probe-corridor refinement, an expanded far-field domain, and kept the Gmsh geometry linear so field order is not confused with geometric interpolation order.

## Retained validation case

Nominal POC-001 configuration:

- mean coil radius: 0.05 m;
- turns: 100;
- current: 1 A;
- winding section: 0.002 m × 0.002 m;
- probe positions: z = -0.10, -0.05, 0, +0.05, +0.10 m;
- nominal air domain: 0.30 m radius × ±0.30 m;
- FEM far-field multiplier: 2.0;
- magnetic solution order: 2;
- convergence mesh sizes: 0.03, 0.02 and 0.012 m, with local refinement scaling with each level.

GitHub Actions validation used Gmsh 4.12.1 and GetDP 3.2.0.

## Observed convergence evidence

For the three retained mesh levels, the generated meshes increased from 7,377 nodes / 15,007 elements to 12,667 / 25,671 and finally 28,361 / 57,225.

The observed maximum relative error against the matching finite-winding analytical oracle was approximately 0.5202%, 0.5220% and 0.5224% respectively. The final two meshes differed in the sampled axial field by only about 0.00415%, demonstrating numerical stabilization rather than merely a single lucky comparison. The finest-mesh RMS relative error was approximately 0.3410%, and its maximum symmetry mismatch was approximately 0.000251%.

At the centre probe, the finest FEM result was approximately 0.001255825 T versus approximately 0.001256553 T for the finite-winding analytical reference.

## Automated acceptance gate

`pvl poc001-fem` now fails with a non-zero exit status unless all retained criteria pass:

- at least 3 mesh levels;
- strictly decreasing characteristic mesh sizes;
- strictly increasing node and element counts;
- every mesh below 1% maximum pointwise relative error;
- finest mesh below 1% maximum pointwise relative error;
- finest mesh below 0.5% RMS relative error;
- final successive sampled-field change below 0.1%;
- finest symmetry mismatch below 0.01%.

These criteria are intentionally much tighter than the earlier 20% integration smoke-test threshold. They are implemented as a reproducible machine gate, not a narrative judgment.

## Reproducibility and evidence

All internal geometry values use SI units. Each configuration produces canonical JSON and a SHA-256 hash. Solver runs preserve configuration, geometry, mesh, GetDP problem file, solver stdout/stderr, raw field cuts, processed probe values, solver versions, mesh counts, convergence metrics and the final validation-gate result.

GitHub Actions installs the external solver stack, executes the tests, generates the analytical reference, runs the full FEM convergence study, enforces the gate and uploads the resulting evidence artifact.

## Commands

```bash
pip install -e ".[dev]"
pytest
pvl doctor
pvl poc001 --output results/poc001
pvl poc001-fem --output results/poc001_fem
```

`pvl doctor` returns a non-zero status when `gmsh` or `getdp` are unavailable. `pvl poc001-fem` returns a non-zero status when the numerical validation gate fails.

## Unit status

PVL-POC-001 has reached a quantitatively validated solver-foundation state for the retained circular-coil benchmark. This validates the ordinary magnetostatic numerical stack only. It does **not** validate the Portal Hypothesis, any anomalous physics, or the full Portal Boundary Physics Rig.

PVL can proceed from this benchmark to the next controlled model while preserving the same rule: established physics and numerical convergence must be exhausted before any residual is treated as potentially anomalous.
