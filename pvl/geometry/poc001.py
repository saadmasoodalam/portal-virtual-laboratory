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
    """
    c = config.coil
    a = config.air
    s = config.source_section
    h_far = config.mesh.characteristic_length_m
    h_coil = min(h_far / 4.0, s.radial_thickness_m / 2.0, s.axial_height_m / 2.0)
    r0 = c.radius_m - s.radial_thickness_m / 2.0
    r1 = c.radius_m + s.radial_thickness_m / 2.0
    y0 = c.center_z_m - s.axial_height_m / 2.0
    y1 = c.center_z_m + s.axial_height_m / 2.0

    return f'''// PVL-POC-001 axisymmetric magnetostatic geometry. SI units: metres.
// x = cylindrical radius; y = physical coil-axis coordinate; rotation axis = y.
Rair = {a.radius_m:.17g};
Hair = {a.half_height_m:.17g};
hFar = {h_far:.17g};
hCoil = {h_coil:.17g};

// Outer air domain.
Point(1) = {{0, -Hair, 0, hFar}};
Point(2) = {{Rair, -Hair, 0, hFar}};
Point(3) = {{Rair, Hair, 0, hFar}};
Point(4) = {{0, Hair, 0, hFar}};
Line(1) = {{1, 2}};
Line(2) = {{2, 3}};
Line(3) = {{3, 4}};
Line(4) = {{4, 1}};
Curve Loop(20) = {{1, 2, 3, 4}};

// Small finite cross-section approximating a filamentary circular coil.
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

Mesh.ElementOrder = {config.mesh.order};
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
