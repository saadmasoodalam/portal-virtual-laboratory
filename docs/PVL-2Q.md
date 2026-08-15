# PVL-2Q — Complete-Rig 3D DC Magnetostatic Solver Gate

Status: implementation candidate

## Objective

PVL-2Q connects the complete-Rig exploratory Gmsh topology validated in PVL-2P to the repository's established magnetostatic solver stack. The unit introduces the first complete-Rig three-dimensional GetDP DC field solve, but it remains an **exploratory solver-validation primitive** until mesh/domain convergence and immutable single-run execution integration are complete.

PVL-2Q contains only ordinary magnetostatics. It does not add an eddy-current term, thermal coupling, anomaly classifier, biological test, Ramal/UBL construct, or Portal Hypothesis term.

## External air boundary

The PVL-2P air domain strictly contains every material primitive. PVL-2Q adds a named two-dimensional physical group for the six external faces of that padded air box:

`PVL_OuterBoundary`

The faces are selected after OpenCASCADE fragmentation by six thin `Surface In BoundingBox` slabs. The MSH2 integrity parser records physical groups by dimension, triangle counts by surface tag, and tetrahedron counts by volume tag. The complete-Rig mesh gate therefore verifies that the outer-boundary physical surface exists and contains mesh triangles before a GetDP solve is permitted.

The finite outer-air box and `A=0` boundary are numerical truncation choices, not a physical boundary of the Rig. Air-domain convergence must pass before the field is treated as stabilized numerical output.

## 3D magnetostatic formulation

The GetDP model uses a magnetic vector potential `a` in an H(curl) edge-element space:

`curl(nu curl a) = j_s`

The weak form contains only the magnetic reluctivity term `nu * curl(a)` and the prescribed source-current-density term `j_s`. The function space uses first-order three-dimensional edge basis functions and a tree-cotree gauge. The external air surface applies the retained zero-vector-potential truncation condition.

The post-processing field is `B = curl(a)`.

## Material treatment

Every complete-Rig physical volume is mapped back to the versioned PVL material library. In this DC magnetostatic unit only relative permeability enters the governing equation.

The retained exploratory steel record uses the existing linear placeholder `mu_r = 100`. Copper, glass, air and the sample medium use their retained scalar relative permeabilities.

This is not a hardware-fidelity ferromagnetic prediction. Real steel requires grade-specific/nonlinear B-H data, saturation/hysteresis treatment, and eventually measured or supplier provenance.

Electrical conductivity is deliberately inactive in PVL-2Q because the state is static DC. Conductivity-driven eddy currents and Joule heating remain in the separately validated POC-004/005 magneto-quasistatic path.

## Homogenized winding source

Each finite winding-envelope volume is treated as a homogenized stranded winding. If the pack cross-section is `A_pack`, the volume current-density magnitude is

`J = N I / A_pack`.

The source direction is an analytic azimuthal field around the coil Y-axis, so the current distribution is divergence-free inside the annular winding volume. Integrating the source through a radial/axial winding-pack cross-section returns exactly `N I`.

PVL checks this normalization before invoking GetDP so the number of turns cannot be applied twice. The exploratory fixture has a positive annular inner radius, so the analytic azimuthal expression never evaluates on its coordinate-axis singularity inside the source volume.

## Electrical polarity versus geometric normal

PVL-2O intentionally records Coil A and Coil B geometric normals as +Y and -Y because the coils lie on opposite sides and their geometry normals point toward the center. Those signs are **not electrical polarity**.

PVL-2Q keeps that distinction explicit: geometric normal is stored only as geometry provenance; positive electrical polarity for both coils is referenced to global +Y; experiment `polarity` supplies the electrical sign.

This preserves the already validated POC-002 convention: equal positive currents have the same electrical sense and their central fields add; changing one polarity produces the opposed-source state. The source must never silently reverse simply because Coil B's geometric normal is -Y.

## Current smoke state

The first CI state remains deliberately simple: exploratory complete-Rig geometry, Coil A = +1 A DC, Coil B = OFF, a 500-turn exploratory winding pack, the retained linear material library, one complete-Rig Gmsh mesh, and one real-valued GetDP magnetostatic solve.

The command is:

`python -m pvl.cli.rig_dc --output results/rig_dc_smoke`

The command records solver versions, mesh counts, outer-boundary triangle count, exact ampere-turn normalization, central-axis B metrics, logs, Gmsh model, mesh, GetDP input and post-processing data.

## Numerical convergence controls

The retained acceptance threshold is 3% for both the five-probe aggregate and center observable. That criterion is not loosened after observing a result.

Local component targets remain:

- winding packs: 2 mm
- steel frame: 5 mm
- distant air: 40 mm graded target
- far-field transition: 100 mm
- near-field grading margin: 25% of retained topology size

The convergence observable is a fixed 4 mm cubic sensor volume centered at each retained Y location: -60, -30, 0, +30 and +60 mm. GetDP evaluates B on a fixed 4x4x4 `OnBox` division grid and PVL computes the B_y volume mean using tensor trapezoidal integration. A topology-derived guard rejects a sensor box that crosses a retained material interface.

## Numerical evidence

### Run #150

Exact fixed-coordinate point probes removed the changing-line-grid interpolation confound but the retained profile still failed convergence. Final 15 -> 12 mm mesh change was 3.391% at the probe set and 1.038% at the center. Final 75% -> 100% air-domain change was 11.320% at the probe set and 8.399% at the center.

### Run #154

The graded far-field candidate exposed a geometry-control corner case on the Rig's thin axis: the numerical near-field grading box inherited the outer domain's absolute 50 mm minimum padding and could coincide with the outer air box. The correction separated numerical near-box padding from physical outer-domain padding. No Maxwell, source, material, boundary, or convergence criterion changed.

### Run #167

Using 12/10/8 mm near-Rig meshes and 100/125/150% air domains with the earlier one-dimensional finite aperture, the solver stack remained healthy but the unchanged convergence gate failed. Final mesh probe change was 4.370%, mesh center 4.588%, domain probe 4.513%, and domain center 3.042%.

### Run #179

The fixed three-dimensional sensor-volume observable isolated the remaining issue. The run passed 155 tests, the complete-Rig mesh integrity gate, the real GetDP DC smoke solve, frontend typecheck/build, finite-field checks, and artifact preservation.

The air-domain axis passed the retained 3% criterion:

- final 125% -> 150% domain probe change: **2.151%**
- final domain center change: **1.377%**

The mesh axis remained outside the gate:

- final 10 -> 8 mm mesh probe change: **4.412%**
- final mesh center change: **3.053%**

This shows that finite-domain truncation is no longer the active numerical blocker at the retained 8 mm shared baseline. The remaining blocker is near-Rig mesh stabilization.

## Current convergence candidate

The mesh sequence is now **10 -> 8 -> 6.4 mm**, preserving a constant 0.8 refinement ratio instead of choosing an arbitrarily small final step merely to reduce the successive-change number.

The air-domain sequence remains **100/125/150% at the shared 8 mm baseline**. This factorized design deliberately isolates the mesh axis while retaining the already-passing air-domain check, and avoids multiplying the cost of the larger-domain solves before the finer mesh is shown to be useful.

If the 6.4 mm mesh sequence passes, PVL-2Q will still require a final air-domain confirmation at the accepted finest mesh before PR #22 can leave draft. Passing the factorized run is not treated as sufficient reason to skip that confirmation.

## Scientific/execution status

An actual Gmsh/GetDP calculation occurs in the PVL-2Q smoke and convergence primitives, so their local solver evidence records `solver_execution=true`.

However, these are **not yet executed immutable PVL experiment runs**. They do not bypass PVL-2N. Exact package checksum, run selection, Rig/material fingerprints, single-run confirmation, no-batch rule and no-biological-testing rule remain mandatory for persisted experiment execution.

## Scientific boundary

A passing PVL-2Q result validates numerical stabilization of an ordinary exploratory finite-element magnetostatic implementation for the retained Rig geometry and material baselines. It does not demonstrate a portal, spacetime coupling, anomalous physics, or a valid high-fidelity prediction of the future physical Rig.

The governing equation, material parameters, winding source normalization, outer boundary condition, sensor-volume definition, and 3% acceptance criterion remain ordinary-physics controls and are not modified by the Portal Hypothesis Layer.

## Merge gate

PR #22 remains draft until all of the following are demonstrated with verifiable evidence:

- GetDP accepts the complete 3D H(curl) formulation and sensor-volume post-processing;
- external-boundary and complete-Rig mesh integrity gates pass;
- the retained 3% mesh convergence gate passes without post-hoc weakening;
- the retained 3% air-domain convergence gate passes at the accepted finest mesh;
- an active source produces finite, non-zero B;
- frontend typecheck/build remains green;
- POC-001 through POC-005 all remain green.
