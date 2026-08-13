# ADR-001 — Primary solver stack

Status: Accepted

## Decision

PVL v0.1 uses **Gmsh** for parametric geometry/meshing and **GetDP** for the primary finite-element electromagnetic solver. Python is the orchestration and validation layer.

FEniCSx is reserved for later independent verification. OpenFOAM is reserved for later fluid/airflow and convective heat-transfer work.

## Rationale

The first required progression is magnetostatics → low-frequency electromagnetic response → induced/eddy currents → Joule heating → thermal coupling. GetDP/Gmsh provides a direct open-source path without requiring PVL to invent a new multiphysics FEM framework.

## Validation gate

The solver is not trusted for Rig v1 until PVL-POC-001 converges toward the analytical on-axis field of a circular coil under mesh refinement.
