# Portal Virtual Laboratory (PVL)

PVL is a reproducible scientific digital-twin environment for the Portal Boundary Physics Rig v1.

The software is deliberately split into two domains:

1. **Established physics** — geometry, meshing, electromagnetics, induced currents, Joule heating, thermal behavior, convergence, validation, and raw simulation data.
2. **Portal Hypothesis Layer** — downstream project-specific analysis only. It must never alter Maxwell equations, material equations, mesh behavior, or solver output.

## Current milestone

**PVL-1B — Solver Stack Proof of Concept and Repository Bootstrap**

The first validation case is a circular DC coil in air. PVL computes the analytical on-axis magnetic field

\[
B(z)=\frac{\mu_0 N I R^2}{2(R^2+z^2)^{3/2}}
\]

and provides the infrastructure for a Gmsh → GetDP → Python FEM result to be compared against it.

The project does not advance to the full Rig v1 digital twin until the FEM solution converges toward the analytical field under mesh refinement.

## Planned stack

- Python 3.12+
- Gmsh — geometry and meshing
- GetDP — primary electromagnetic FEM
- FastAPI — simulation backend
- NumPy / Pandas — numerical analysis and export
- meshio / VTK — field interchange
- React + TypeScript + Three.js / React Three Fiber — interactive 3D laboratory
- ParaView — scientific field inspection
- FEniCSx — later independent FEM verification
- OpenFOAM — later airflow/fluid/convective heat-transfer extension

## Scientific rules

- SI units internally.
- Every experiment configuration is serializable and hashable.
- Preserve raw inputs, meshes, logs, fields, metrics, and environment metadata.
- No result may exist only as a screenshot or graph.
- No portal effect is inserted into the physics solver.
- Ordinary electromagnetic, thermal, numerical, and sensor explanations are tested before any hypothesis-layer classification.

## Development

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -e ".[dev]"
pytest
```

For FEM execution, install `gmsh` and `getdp` so their executables are available on `PATH` (or configure explicit executable paths later in PVL settings).

## Repository status

PVL-1A architecture: complete.

PVL-1B bootstrap: in progress.
