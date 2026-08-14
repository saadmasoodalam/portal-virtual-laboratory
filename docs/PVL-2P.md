# PVL-2P — Complete-Rig Exploratory Gmsh Geometry and Mesh Gate

Status: implementation candidate

## Objective

PVL-2P consumes the coordinate and constructive-topology contract frozen in PVL-2O and generates the first complete-Rig exploratory three-dimensional Gmsh model. The unit stops at CAD/mesh integrity. It does not invoke GetDP and does not calculate electromagnetic, thermal, anomaly, or Portal Hypothesis results.

The purpose is to prove that the steel frame, isolated copper boundary, sample chamber, two winding envelopes, and surrounding air can coexist as an explicit conformal finite-element topology with auditable physical-volume identities before PVL permits any full-Rig field solve.

## Geometry source and fidelity

The CI smoke model uses `architecture_example_rig_v1()`. Values fixed by the approved PVL architecture example are tagged `illustrative`; missing 3D construction details required for meshing are filled only by named exploratory conventions and are likewise tagged `illustrative`.

The fixture is therefore **not hardware-fidelity geometry**. Its purpose is software/solver-topology validation.

In particular, the fixture preserves:

- 400 × 300 mm planar steel-frame envelope;
- 25 mm steel member width and 20 mm Z extrusion;
- 300 × 200 mm copper boundary;
- 1 mm copper thickness and 5 mm deliberate gap;
- 70 mm sample outer diameter and 100 mm height;
- Coil A/B centers at Y = −120/+120 mm and 500 turns.

Copper strip width, chamber wall thickness, and winding-envelope cross-section dimensions remain explicit exploratory conventions because the source does not fix them at hardware fidelity.

## OpenCASCADE construction

The generated `.geo` file uses the OpenCASCADE kernel. Constructive primitives are converted as follows:

- steel and copper strip primitives → `Box` volumes;
- sample medium → cylinder;
- sample wall → outer cylinder minus inner cylinder;
- each winding envelope → annular cylinder aligned with its normalized geometric coil axis;
- surrounding air → padded box enclosing every material primitive.

The material volumes are removed from the initial air solid and then fragmented with the air region so the resulting model presents conformal shared interfaces for later FEM formulations.

PVL requests OpenCASCADE Boolean-number preservation and then validates that the expected physical regions actually survive into the mesh. Number preservation is therefore never trusted without a mesh-level check.

## Physical-volume contract

Every material primitive receives exactly one deterministic physical volume and the air region receives its own physical volume. Physical names are derived deterministically from constructive primitive IDs, for example:

- `PVL_Air`
- `PVL_steel_north`
- `PVL_steel_south`
- `PVL_copper_east_south`
- `PVL_sample_wall`
- `PVL_sample_medium`
- `PVL_winding_coil_a`
- `PVL_winding_coil_b`

The persisted Gmsh manifest stores the source Rig fingerprint, constructive-topology fingerprint, Gmsh configuration hash, air bounds, physical tags, elementary volume tags, material IDs, and the explicit `solver_execution=false` boundary.

## Air domain

Air bounds are calculated from actual constructive primitive bounds rather than hidden constants. Each axis is padded by the larger of:

- `air_margin_fraction × material extent`, or
- `air_min_margin_m`.

The air domain is a numerical boundary for future FEM work, not a claim that its default size is already electromagnetically converged. Full field-domain convergence remains a later solver gate.

## Mesh configuration

PVL-2P produces first-order MSH 2.2 tetrahedra because the repository already has a deterministic ASCII MSH2 parsing path and CI runs Gmsh through the command-line executable. Geometry/mesh parameters are explicit and hashable in `RigGmshConfig`.

The default smoke configuration uses a coarse global maximum characteristic length while allowing smaller elements around thin geometry. This is a topology/mesh-health test only, not the final scientific mesh resolution.

## Independent MSH2 integrity parser

PVL-2P parses the generated ASCII MSH2 file directly and does not infer success from Gmsh's process exit code alone. It verifies:

- declared versus parsed node count;
- declared versus parsed element count;
- presence of first-order tetrahedra;
- physical-volume names;
- physical tag on every tetrahedron;
- tetrahedron count per physical volume;
- positive tetrahedron volume;
- tetrahedral mean-ratio quality.

For a tetrahedron of volume `V` and six edge lengths `l_i`, the PVL mesh-health metric is

`q = 12 (3V)^(2/3) / sum(l_i^2)`.

An equilateral tetrahedron has `q = 1`; a degenerate tetrahedron approaches zero. PVL labels this explicitly as its mesh-health metric and does not claim it is identical to a named Gmsh API quality metric.

## Validation gate

The complete-Rig mesh gate requires:

- at least one node and one tetrahedron;
- exact expected physical-volume name set;
- exact expected tetrahedral physical-tag set;
- at least one tetrahedron in every required physical volume;
- populated air region;
- tetrahedral volume above the numerical positivity floor;
- minimum mean-ratio quality at or above the retained smoke threshold;
- `solver_execution=false`.

The gate persists:

- `rig_v1.geo`;
- `rig_v1.msh`;
- `constructive_topology.json`;
- `gmsh_manifest.json`;
- `mesh_metrics.json`;
- `validation_gate.json`;
- Gmsh stdout/stderr logs.

These are uploaded with the existing PVL CI evidence artifact.

## CI command

`python -m pvl.cli.rig_mesh --output results/rig_mesh_smoke`

The command returns a nonzero status if Gmsh is missing or the mesh gate fails.

## Scientific boundary

PVL-2P is ordinary CAD and numerical-mesh validation. It contains no GetDP formulation, no field solve, no material response calculation, no anomaly classifier, no biological test, and no Portal Hypothesis term.

A passing PVL-2P gate only means the exploratory complete-Rig geometry can be converted into an auditable tetrahedral mesh with the expected material-region topology.

## Next unit

PVL-2Q should connect the already validated magnetostatic GetDP physics to exactly one selected DC Rig run, using PVL-2P physical groups and the PVL-2N single-run execution boundary. Before that solve is treated as scientific output, PVL-2Q must add outer-air-domain and mesh-refinement convergence checks and retain POC-001 through POC-005 as permanent regressions.
