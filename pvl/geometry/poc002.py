from __future__ import annotations

from pathlib import Path

from pvl.core.models import POC002Config


def render_axisymmetric_gmsh_geo(config: POC002Config) -> str:
    """Render the two-coil axisymmetric FEM section for PVL-POC-002."""
    a = config.air
    s = config.source_section
    h_far = config.mesh.characteristic_length_m
    h_coil = min(h_far / 30.0, s.radial_thickness_m / 2.0, s.axial_height_m / 2.0)
    h_probe = h_far / 20.0
    r_air = a.fem_radius_m
    h_air = a.fem_half_height_m
    probe_y0 = min(config.probe_z_m) - 2.0 * h_far
    probe_y1 = max(config.probe_z_m) + 2.0 * h_far
    probe_rmax = min(min(config.coil_a.radius_m, config.coil_b.radius_m) * 0.20, 0.01)

    def bounds(coil):
        return (
            coil.radius_m - s.radial_thickness_m / 2.0,
            coil.radius_m + s.radial_thickness_m / 2.0,
            coil.center_z_m - s.axial_height_m / 2.0,
            coil.center_z_m + s.axial_height_m / 2.0,
        )

    ar0, ar1, ay0, ay1 = bounds(config.coil_a)
    br0, br1, by0, by1 = bounds(config.coil_b)

    return f'''// PVL-POC-002 dual-coil axisymmetric geometry. SI units: metres.
// x = cylindrical radius; y = physical coil-axis coordinate; rotation axis = y.
Rair = {r_air:.17g};
Hair = {h_air:.17g};
hFar = {h_far:.17g};
hCoil = {h_coil:.17g};
hProbe = {h_probe:.17g};

Point(1) = {{0, -Hair, 0, hFar}};
Point(2) = {{Rair, -Hair, 0, hFar}};
Point(3) = {{Rair, Hair, 0, hFar}};
Point(4) = {{0, Hair, 0, hFar}};
Line(1) = {{1, 2}};
Line(2) = {{2, 3}};
Line(3) = {{3, 4}};
Line(4) = {{4, 1}};
Curve Loop(20) = {{1, 2, 3, 4}};

// Coil A finite winding section.
Point(10) = {{{ar0:.17g}, {ay0:.17g}, 0, hCoil}};
Point(11) = {{{ar1:.17g}, {ay0:.17g}, 0, hCoil}};
Point(12) = {{{ar1:.17g}, {ay1:.17g}, 0, hCoil}};
Point(13) = {{{ar0:.17g}, {ay1:.17g}, 0, hCoil}};
Line(10) = {{10, 11}};
Line(11) = {{11, 12}};
Line(12) = {{12, 13}};
Line(13) = {{13, 10}};
Curve Loop(21) = {{10, 11, 12, 13}};

// Coil B finite winding section.
Point(20) = {{{br0:.17g}, {by0:.17g}, 0, hCoil}};
Point(21) = {{{br1:.17g}, {by0:.17g}, 0, hCoil}};
Point(22) = {{{br1:.17g}, {by1:.17g}, 0, hCoil}};
Point(23) = {{{br0:.17g}, {by1:.17g}, 0, hCoil}};
Line(20) = {{20, 21}};
Line(21) = {{21, 22}};
Line(22) = {{22, 23}};
Line(23) = {{23, 20}};
Curve Loop(22) = {{20, 21, 22, 23}};

// Conformal air region with two winding holes.
Plane Surface(30) = {{20, 21, 22}};
Plane Surface(31) = {{21}};
Plane Surface(32) = {{22}};

Physical Surface("Air", 1) = {{30}};
Physical Surface("CoilA", 2) = {{31}};
Physical Surface("CoilB", 3) = {{32}};
Physical Curve("Boundary", 10) = {{1, 2, 3, 4}};
Physical Curve("Axis", 11) = {{4}};

// Scaled near-axis refinement keeps field-probe extraction convergent.
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
// GetDP controls the magnetic approximation order; keep geometry linear.
Mesh.ElementOrder = 1;
Mesh.MshFileVersion = 2.2;
'''


def write_axisymmetric_gmsh_geo(config: POC002Config, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_axisymmetric_gmsh_geo(config), encoding="utf-8")
    return path
