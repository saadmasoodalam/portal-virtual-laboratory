# Unit PVL-1B — Solver Stack Proof of Concept and Repository Bootstrap

## Objective

Create the executable Python foundation for PVL and establish the first numerical validation problem before implementing the full Portal Boundary Physics Rig v1.

## Implemented in this unit

- installable Python package and CLI;
- immutable, validated experiment configuration;
- deterministic SHA-256 configuration hashing;
- analytical circular-coil magnetic-field reference;
- parameterized Gmsh POC-001 geometry generator;
- external Gmsh/GetDP executable discovery;
- FEM-versus-analytic comparison metrics;
- automated unit tests.

## POC-001 gate

For an ideal circular N-turn coil, the analytical on-axis field is:

`B(z) = μ0 N I R² / (2 (R² + z²)^(3/2))`

Full Rig v1 implementation remains blocked until a GetDP numerical solution demonstrates mesh convergence toward this analytical reference.

## Reproducibility

All internal geometry values use SI units. The configuration model produces canonical JSON and a SHA-256 hash. Future solver runs preserve configuration, mesh, solver input, stdout/stderr, raw fields, processed fields, metrics, and environment metadata.

## Local verification

```bash
pip install -e ".[dev]"
pytest
pvl poc001 --output results/poc001
pvl doctor
```

`pvl doctor` returns a non-zero status when `gmsh` or `getdp` are unavailable.

## Environment note

The implementation was unit-tested against the analytical/reference layer. The current development runtime used to prepare this branch does not contain the external `gmsh` and `getdp` executables, so the actual FEM solve is the next gate rather than being represented as already validated.
