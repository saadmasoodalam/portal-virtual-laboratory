# PVL-2O — Rig Coordinate Convention and Constructive Topology Contract

Status: implementation candidate

## Objective

PVL-2O resolves the geometric ambiguity that must be removed before PVL can generate a constructive Gmsh model of the complete Portal Boundary Physics Rig v1.

The Rig v1 source describes four steel/iron pieces fixed to a nonconductive base as a square or rectangle, an electrically isolated inner copper boundary with a deliberate gap, a central sample vessel, and two matched coils on opposite sides. The approved PVL-1A architecture likewise models the steel structure as north/south/east/west members rather than a three-dimensional cage.

PVL-2O therefore does **not** generate a FEM mesh or solve a field. It freezes coordinate meaning, turns the solver-neutral Rig manifest into an explicit exploratory constructive topology, and records every unresolved geometric convention instead of hiding it in future Gmsh code.

## Coordinate convention

PVL now uses `pvl-rig-v1-top-view-xyz-v1`:

- +X: top-view west-to-east horizontal direction;
- +Y: top-view south-to-north direction through Coil A, the central chamber and Coil B;
- +Z: normal to the nonconductive base plane, positive upward;
- origin: nominal Rig geometric center at the sample-chamber centerline;
- units: SI metres;
- handedness: right-handed.

Coil A's default geometric normal is +Y and Coil B's is -Y so both point toward the central axis from opposite sides. This is only a geometry convention. Coil current polarity and field direction remain independent experiment variables.

## Compatibility mapping for existing Rig schema

Earlier PVL schema names were already serialized by the frontend and experiment-package stack. PVL-2O preserves them and freezes their meaning rather than silently renaming fields:

| Existing field | Frozen PVL-2O meaning |
|---|---|
| `frame.outer_width` | top-view X span |
| `frame.outer_depth` | top-view Y span; legacy name corresponding to the planar frame height/depth in the earlier implementation |
| `frame.outer_height` | declared Z envelope; legacy name |
| `frame.member_width` | in-plane steel-bar width |
| `frame.member_thickness` | physical steel-bar Z extrusion |
| `copper_boundary.outer_width` | top-view X span |
| `copper_boundary.outer_depth` | top-view Y span |
| `copper_boundary.strip_width` | in-plane copper-strip width |
| `copper_boundary.thickness` | copper Z extrusion |

This compatibility mapping allows the approved 400 × 300 mm top-view frame, 25 mm bar width and 20 mm physical depth example to be represented as `outer_width=0.400`, `outer_depth=0.300`, `outer_height=0.020`, `member_width=0.025`, and `member_thickness=0.020` metres.

If `frame.outer_height` exceeds `member_thickness`, constructive geometry uses `member_thickness` as the physical steel extrusion and records a warning. A member thickness greater than the declared envelope is rejected.

## Steel topology

The previous solver-neutral `FRAME_ENVELOPE` remains available for preview/bounds work, but PVL-2O adds four explicit constructive steel boxes:

- `steel:north`
- `steel:south`
- `steel:east`
- `steel:west`

North and south members span the complete X width. East and west members occupy only the Y distance between the north and south members. This produces an overlap-free rectangular frame with the correct outer envelope and a central opening.

The source material does not specify measured corner-joint construction. Consequently this butt-joint representation is marked as an **exploratory topology idealization**, not hardware-fidelity joint geometry.

## Copper topology and deliberate gap

PVL-2O represents the copper boundary as explicit rectangular strip primitives. It must fit inside the open steel rectangle and remain electrically isolated from the steel.

The Rig v1 source requires a deliberate gap but does not identify which side contains it. A hidden hard-coded choice would violate the PVL requirement that important geometry be editable, serialized and hashed. `BoundaryGeometry` therefore now contains the explicit enum `gap_side = north | south | east | west`.

The default is `east`, clearly labeled as an exploratory PVL modeling convention. Changing the side changes both the Rig definition fingerprint and constructive-topology fingerprint.

For an open baseline, the selected copper side is divided into two primitives separated by exactly `gap_width`. For a closed baseline, the four continuous strips are retained while the configured gap width/side remain part of the Rig definition for controlled-state work.

## Sample and coil checks

The constructive compiler rejects configurations in which:

- steel member width removes the central opening;
- steel member thickness exceeds the declared Z envelope;
- the copper boundary does not fit inside the steel-frame opening;
- copper strip width removes the copper inner opening;
- copper is declared electrically connected to the steel;
- the selected open gap is too wide for its side;
- the sample chamber does not fit inside the copper inner opening;
- chamber wall thickness is at least the chamber radius;
- a coil has missing/non-positive geometric dimensions or turn count.

The sample chamber remains a Z-axis cylindrical shell plus contained medium volume. Coils remain winding-envelope primitives with normalized axes. Their axis metadata explicitly states that geometric normal is not electrical field polarity.

## Provenance and hashing

`RigConstructiveTopology` stores:

- topology schema version;
- Rig ID;
- source Rig-definition SHA-256 fingerprint;
- complete coordinate-convention object;
- topology fidelity classification;
- source hardware-fidelity readiness;
- declared frame envelope;
- every constructive primitive;
- unresolved-topology warnings.

Its SHA-256 fingerprint is deterministic over the canonical serialized model.

The existing solver-neutral Rig geometry manifest now also carries the explicit coordinate-convention ID, field-semantic metadata and copper-gap provenance.

## Scientific boundary

PVL-2O is an ordinary geometry/topology unit. It contains no electromagnetic solver change, no anomaly classifier and no Portal Hypothesis term.

The constructive topology is not yet a hardware-fidelity geometry merely because it is solver-oriented. Joint style and copper-gap side remain explicitly provenance-limited conventions until measured or specified hardware data replaces them.

## Validation gate

PVL-2O acceptance requires:

- source-consistent default Coil A/B geometric normals;
- four distinct non-overlapping steel pieces;
- explicit open copper loop with exact gap width;
- no positive-volume self-overlap within the steel or copper piece sets;
- copper-inside-steel validation;
- chamber-inside-copper validation;
- deterministic topology fingerprints;
- changed gap side changes the Rig/topology identity;
- solver-neutral manifest records coordinate and gap provenance;
- all existing Python/API/frontend and POC-001 through POC-005 regressions remain green.

## Next unit

PVL-2P should consume this topology contract and generate the first complete-Rig exploratory Gmsh geometry. It must preserve primitive IDs as physical groups, create an explicit surrounding air domain, verify Boolean/topological integrity and mesh quality, and remain blocked from scientific use until mesh-convergence checks pass. No Portal Hypothesis term is permitted in that geometry or solver path.
