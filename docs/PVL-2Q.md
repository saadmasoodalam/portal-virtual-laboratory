# PVL-2Q — Complete-Rig 3D DC Magnetostatic Solver Gate

Status: implementation candidate

## Objective

PVL-2Q connects the complete-Rig exploratory Gmsh topology validated in PVL-2P to the repository's established magnetostatic solver stack. The unit introduces the first complete-Rig three-dimensional GetDP DC field solve, but it remains an **exploratory solver-validation primitive** until mesh/domain convergence and immutable single-run execution integration are complete.

PVL-2Q contains only ordinary magnetostatics. It does not add an eddy-current term, thermal coupling, anomaly classifier, biological test, or Portal Hypothesis term.

## External air boundary

The PVL-2P air domain already strictly contains every material primitive. PVL-2Q adds a named two-dimensional physical group for the six external faces of that padded air box:

`PVL_OuterBoundary`

The faces are selected after OpenCASCADE fragmentation by six thin `Surface In BoundingBox` slabs. The MSH2 integrity parser now records physical groups by dimension, triangle counts by surface tag, and tetrahedron counts by volume tag. The complete-Rig mesh gate therefore verifies that the outer-boundary physical surface exists and contains mesh triangles before a GetDP solve is permitted.

The finite outer-air box and `A=0` boundary are numerical truncation choices, not a physical boundary of the Rig. PVL-2Q must add air-domain convergence before treating the field as scientific output.

## 3D magnetostatic formulation

The GetDP model uses a magnetic vector potential `a` in an H(curl) edge-element space:

`curl(nu curl a) = j_s`

The weak form contains only:

- magnetic reluctivity term `nu * curl(a)`;
- prescribed source-current-density term `j_s`.

The function space uses first-order three-dimensional edge basis functions and a tree-cotree gauge. The external air surface applies the retained zero-vector-potential truncation condition.

The post-processing field is

`B = curl(a)`.

The CI smoke solve extracts `B` along the central Y-axis and also writes a source-current visualization.

## Material treatment

Every complete-Rig physical volume is mapped back to the versioned PVL material library. In this DC magnetostatic unit only relative permeability enters the governing equation.

The retained exploratory steel record uses the existing linear placeholder `mu_r = 100`. Copper, glass, air and the sample medium use their retained scalar relative permeabilities.

This is not a hardware-fidelity ferromagnetic prediction. Real steel requires grade-specific/nonlinear B-H data, saturation/hysteresis treatment, and eventually measured or supplier provenance.

Electrical conductivity is deliberately inactive in PVL-2Q because the state is static DC. Conductivity-driven eddy currents and Joule heating remain in the separately validated POC-004/005 magneto-quasistatic path.

## Homogenized winding source

Each finite winding-envelope volume is treated as a homogenized stranded winding. If the pack cross-section is `A_pack`, the volume current-density magnitude is

`J = N I / A_pack`.

The source direction is an analytic azimuthal field around the coil Y-axis, so the current distribution is divergence-free inside the annular winding volume. Integrating the source through a radial/axial winding-pack cross-section returns exactly

`N I`.

PVL explicitly checks this normalization before invoking GetDP so the number of turns cannot be applied twice.

The exploratory fixture has a positive annular inner radius, so the analytic azimuthal expression never evaluates on its coordinate-axis singularity inside the source volume.

## Electrical polarity versus geometric normal

PVL-2O intentionally records Coil A and Coil B geometric normals as +Y and -Y because the coils lie on opposite sides and their geometry normals point toward the center. Those signs are **not electrical polarity**.

PVL-2Q keeps that distinction explicit:

- geometric normal is stored only as geometry provenance;
- positive electrical polarity for both coils is referenced to global +Y;
- experiment `polarity` supplies the electrical sign.

This preserves the already validated POC-002 convention: equal positive currents have the same electrical sense and their central fields add; changing one polarity produces the opposed-source state. The source must never silently reverse simply because Coil B's geometric normal is -Y.

## Current smoke state

The first CI state is deliberately simple:

- exploratory complete-Rig geometry;
- Coil A = +1 A DC;
- Coil B = OFF;
- 500-turn exploratory winding pack;
- linear retained material library;
- one complete-Rig Gmsh mesh;
- one real-valued GetDP magnetostatic solve.

The command is:

`python -m pvl.cli.rig_dc --output results/rig_dc_smoke`

The command records solver versions, mesh counts, outer-boundary triangle count, exact ampere-turn normalization, central-axis B metrics, logs, Gmsh model, mesh, GetDP input and post-processing data.

## Scientific/execution status

An actual Gmsh/GetDP calculation occurs in the PVL-2Q smoke primitive, so its local solver evidence records `solver_execution=true`.

However, it is **not yet an executed immutable PVL experiment run**. It does not bypass PVL-2N. The scientific execution overlay will only be extended after this complete-Rig solver primitive passes syntax/runtime validation plus mesh and air-domain convergence. Exact package checksum, run selection, Rig/material fingerprints, single-run confirmation, no-batch rule and no-biological-testing rule remain mandatory for persisted experiment execution.

## Initial acceptance gate

Before adding convergence, the first PVL-2Q checkpoint requires:

- complete-Rig Gmsh mesh gate passes;
- named external boundary exists and is populated by triangles;
- source `J A_pack = N I` normalization passes for both coils;
- GetDP accepts the three-dimensional H(curl)/tree-cotree formulation;
- active source produces finite, non-zero B values;
- no frequency-domain, Joule, thermal, anomaly or Portal term enters the formulation;
- frontend remains green;
- POC-001 through POC-005 remain green.

A syntax/runtime failure is treated as a solver implementation failure and corrected rather than normalized away.

## Convergence gate before scientific use

After the first smoke solve passes, PVL-2Q should retain multiple mesh levels and multiple outer-air margins. At minimum it should compare stable central/axis B metrics, mesh complexity and final successive changes. Tolerances will be chosen from observed numerical behavior and documented; they must not be loosened merely to make a run pass.

Only after both mesh refinement and air-domain truncation stabilize should PVL integrate this solver with the immutable PVL-2N selected-run execution path.

## Scientific boundary

A passing PVL-2Q result validates an ordinary exploratory finite-element magnetostatic implementation for the retained Rig geometry and material baselines. It does not demonstrate a portal, spacetime coupling, anomalous physics, or a valid high-fidelity prediction of the future physical Rig.
