from __future__ import annotations

from pathlib import Path

from pvl.core.models import POC001Config


def render_gmsh_geo(config: POC001Config) -> str:
    """Render the original 3D geometry smoke-test model.

    This deliberately remains a geometry-only model. The validated magnetostatic POC uses
    ``render_axisymmetric_gmsh_geo`` below, which represents the circular coil as the solid of
    revolution of a small rectangular current-source section.
    """
    c = config.coil
    a = config.air
    h = config.mesh.characteristic_length_m
    return f'''// PVL-POC-001 generated 3D geometry smoke test. SI units: metres.
SetFactory("OpenCASCADE");
lc = {h:.17g};
Rair = {a.radius_m:.17g};
Hair = {a.half_height_m:.17g};
Rcoil = {c.radius_m:.17g};
Zcoil = {c.center_z_m:.17g};
Cylinder(1) = {{0, 0, -Hair, 0, 0, 2*Hair, Rair}};
Circle(101) = {{0, 0, Zcoil, Rcoil, 0, 2*Pi}};
Physical Volume("air", 1) = {{1}};
Physical Curve("coil", 101) = {{101}};
Mesh.CharacteristicLengthMin = lc;
Mesh.CharacteristicLengthMax = lc;
Mesh.ElementOrder = {config.mesh.order};
'''


def render_axisymmetric_gmsh_geo(config: POC001Config) -> str:
    """Render the 2D axisymmetric FEM geometry used by PVL-POC-001.

    GetDP's axisymmetric Jacobian assumes a model in the z=0 plane with the y-axis as the
    rotation axis. The x coordinate therefore represents cylindrical radius and y represents
    the physical coil-axis coordinate. A rectangular source section centred at x=Rcoil is
    revolved conceptually around the y-axis by the axisymmetric formulation.

    The far-field boundary is deliberately expanded beyond the nominal smoke-test domain, and
    every convergence level scales the source and probe-corridor mesh sizes together. This
    avoids the earlier pseudo-convergence case where only the remote air mesh was refined while
    the winding-source mesh stayed clamped at a fixed size.

    The geometrical mesh remains first-order even when ``MeshConfig.order`` is 2. The second-
    order solution space is hierarchical and is supplied by GetDP through
    ``BF_PerpendicularEdge_2E``. Curving the Gmsh triangles would instead create ``Triangle2``
    geometry elements and conflate solution-polynomial order with geometry interpolation.
    """
    c = config.coil
    a = config.air
    s = config.source_section
    h_far = config.mesh.characteristic_length_m
    h_coil = min(h_far / 30.0, s.radial_thickness_m / 2.0, s.axial_height_m / 2.0)
    h_probe = h_far / 20.0
    r_air = a.fem_radius_m
    h_air = a.fem_half_height_m
    r0 = c.radius_m - s.radial_thickness_m / 2.0
    r1 = c.radius_m + s.radial_thickness_m / 2.0
    y0 = c.center_z_m - s.axial_height_m / 2.0
    y1 = c.center_z_m + s.axial_height_m / 2.0
    probe_y0 = min(config.probe_z_m) - 2.0 * h_far
    probe_y1 = max(config.probe_z_m) + 2.0 * h_far
    probe_rmax = min(c.radius_m * 0.20, 0.01)

    return f'''// PVL-POC-001 axisymmetric magnetostatic geometry. SI units: metres.
// x = cylindrical radius; y = physical coil-axis coordinate; rotation axis = y.
Rair = {r_air:.17g};
Hair = {h_air:.17g};
hFar = {h_far:.17g};
hCoil = {h_coil:.17g};
hProbe = {h_probe:.17g};

// Expanded outer air domain reduces artificial Dirichlet-boundary influence.
Point(1) = {{0, -Hair, 0, hFar}};
Point(2) = {{Rair, -Hair, 0, hFar}};
Point(3) = {{Rair, Hair, 0, hFar}};
Point(4) = {{0, Hair, 0, hFar}};
Line(1) = {{1, 2}};
Line(2) = {{2, 3}};
Line(3) = {{3, 4}};
Line(4) = {{4, 1}};
Curve Loop(20) = {{1, 2, 3, 4}};

// Finite cross-section representing the homogenized circular winding.
Point(10) = {{{r0:.17g}, {y0:.17g}, 0, hCoil}};
Point(11) = {{{r1:.17g}, {y0:.17g}, 0, hCoil}};
Point(12) = {{{r1:.17g}, {y1:.17g}, 0, hCoil}};
Point(13) = {{{r0:.17g}, {y1:.17g}, 0, hCoil}};
Line(10) = {{10, 11}};
Line(11) = {{11, 12}};
Line(12) = {{12, 13}};
Line(13) = {{13, 10}};
Curve Loop(21) = {{10, 11, 12, 13}};

// Air has a conformal hole occupied by the coil source section.
Plane Surface(30) = {{20, 21}};
Plane Surface(31) = {{21}};

Physical Surface("Air", 1) = {{30}};
Physical Surface("Coil", 2) = {{31}};
Physical Curve("Boundary", 10) = {{1, 2, 3, 4}};
Physical Curve("Axis", 11) = {{4}};

// Pointwise B from a first-order A formulation is piecewise constant inside each
// triangle. Refine a narrow corridor around the symmetry axis so probe extraction
// converges with the rest of the mesh instead of jumping between large triangles.
Field[1] = Box;
Field[1].VIn = hProbe;
Field[1].VOut = hFar;
Field[1].XMin = 0;
Field[1].XMax = {probe_rmax:.17g};
Field[1].YMin = {probe_y0:.17g};
Field[1].YMax = {probe_y1:.17g};
Field[1].Thickness = hFar;
Background Field = 1;

Mesh.MeshSizeFromPoints = 1;
// Keep geometry linear. GetDP controls the magnetic approximation order.
Mesh.ElementOrder = 1;
Mesh.MshFileVersion = 2.2;
'''


def write_gmsh_geo(config: POC001Config, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_gmsh_geo(config), encoding="utf-8")
    return path


def write_axisymmetric_gmsh_geo(config: POC001Config, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_axisymmetric_gmsh_geo(config), encoding="utf-8")
    return path
