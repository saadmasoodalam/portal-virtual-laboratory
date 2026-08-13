# ADR-002 — Physics / hypothesis boundary

Status: Accepted

## Rule

The Portal Hypothesis Analyzer is downstream of the established-physics solver and may never modify Maxwell equations, constitutive material equations, mesh generation, solver convergence behavior, or raw physical outputs.

## Layers

1. Established physics: B, H, E, J, flux, energy density, Joule heating, temperature.
2. Derived experimental metrics: deltas, gradients, convergence, clustering, hysteresis, repeatability.
3. Portal hypothesis analysis: project constructs such as Ψ, ΔΨ, F and candidate C classification.

A candidate hypothesis classification is not a FEM-predicted portal state.
