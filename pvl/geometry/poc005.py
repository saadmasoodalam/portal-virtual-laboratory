from __future__ import annotations

import math
from pathlib import Path

from pvl.core.poc005_models import POC005Config


def render_axisymmetric_gmsh_geo(config: POC005Config) -> str:
    """Render the conformal two-coil plus annular-conductor POC-005 geometry."""
    s = config.source_section
    insert = config.insert
    h_far = config.mesh.characteristic_length_m
    h_coil = min(
        h_far / 15.0,
        s.radial_thickness_m / 3.0,
        s.axial_height_m / 3.0,
    )
    if math.isfinite(config.insert_skin_depth_m):
        h_insert = min(
            h_far / 8.0,
            config.insert_skin_depth_m / 3.0,
            (insert.outer_radius_m - insert.inner_radius_m) / 4.0,
            insert.axial_thickness_m / 3.0,
        )
    else:
        h_insert = min(
            h_far / 8.0,
            (insert.outer_radius_m - insert.inner_radius_m) / 4.0,
            insert.axial_thickness_m / 3.0,
        )
    h_probe = h_far / 20.0
    r_air = config.air.fem_radius_m
    h_air = config.air.fem_half_height_m
    probe_y0 = min(config.axis_probe_z_m) - 2.0 * h_far
    probe_y1 = max(config.axis_probe_z_m) + 2.0 * h_far
    probe_rmax = min(min(config.coil_a.radius_m, config.coil_b.radius_m) * 0.20, 0.01)

    def coil_bounds(coil):
        return (
            coil.radius_m - s.radial_thickness_m / 2.0,
            coil.radius_m + s.radial_thickness_m / 2.0,
            coil.center_z_m - s.axial_height_m / 2.0,
            coil.center_z_m + s.axial_height_m / 2.0,
        )

    ar0, ar1, ay0, ay1 = coil_bounds(config.coil_a)
    br0, br1, by0, by1 = coil_bounds(config.coil_b)
    ir0 = insert.inner_radius_m
    ir1 = insert.outer_radius_m
    iy0 = insert.center_z_m - insert.axial_thickness_m / 2.0
    iy1 = insert.center_z_m + insert.axial_thickness_m / 2.0
    insert_box_pad = max(h_far, 2.0 * h_insert)

    return f'''// PVL-POC-005 dual-coil plus conductive annular insert. SI units: metres.
// x = cylindrical radius; y = physical coil-axis coordinate; rotation axis = y.
Rair = {r_air:.17g};
Hair = {h_air:.17g};
hFar = {h_far:.17g};
hCoil = {h_coil:.17g};
hInsert = {h_insert:.17g};
hProbe = {h_probe:.17g};

// Expanded outer air domain.
Point(1) = {{0, -Hair, 0, hFar}};
Point(2) = {{Rair, -Hair, 0, hFar}};
Point(3) = {{Rair, Hair, 0, hFar}};
Point(4) = {{0, Hair, 0, hFar}};
Line(1) = {{1, 2}};
Line(2) = {{2, 3}};
Line(3) = {{3, 4}};
Line(4) = {{4, 1}};
Curve Loop(20) = {{1, 2, 3, 4}};

// Coil A source section.
Point(10) = {{{ar0:.17g}, {ay0:.17g}, 0, hCoil}};
Point(11) = {{{ar1:.17g}, {ay0:.17g}, 0, hCoil}};
Point(12) = {{{ar1:.17g}, {ay1:.17g}, 0, hCoil}};
Point(13) = {{{ar0:.17g}, {ay1:.17g}, 0, hCoil}};
Line(10) = {{10, 11}};
Line(11) = {{11, 12}};
Line(12) = {{12, 13}};
Line(13) = {{13, 10}};
Curve Loop(21) = {{10, 11, 12, 13}};

// Coil B source section.
Point(20) = {{{br0:.17g}, {by0:.17g}, 0, hCoil}};
Point(21) = {{{br1:.17g}, {by0:.17g}, 0, hCoil}};
Point(22) = {{{br1:.17g}, {by1:.17g}, 0, hCoil}};
Point(23) = {{{br0:.17g}, {by1:.17g}, 0, hCoil}};
Line(20) = {{20, 21}};
Line(21) = {{21, 22}};
Line(22) = {{22, 23}};
Line(23) = {{23, 20}};
Curve Loop(22) = {{20, 21, 22, 23}};

// Finite annular conductor cross-section. Revolving this rectangle around y forms
// an axisymmetric conducting ring; it is deliberately separated from both source coils.
Point(30) = {{{ir0:.17g}, {iy0:.17g}, 0, hInsert}};
Point(31) = {{{ir1:.17g}, {iy0:.17g}, 0, hInsert}};
Point(32) = {{{ir1:.17g}, {iy1:.17g}, 0, hInsert}};
Point(33) = {{{ir0:.17g}, {iy1:.17g}, 0, hInsert}};
Line(30) = {{30, 31}};
Line(31) = {{31, 32}};
Line(32) = {{32, 33}};
Line(33) = {{33, 30}};
Curve Loop(23) = {{30, 31, 32, 33}};

// Conformal partition: air contains three holes occupied by CoilA, CoilB and Insert.
Plane Surface(40) = {{20, 21, 22, 23}};
Plane Surface(41) = {{21}};
Plane Surface(42) = {{22}};
Plane Surface(43) = {{23}};

Physical Surface("Air", 1) = {{40}};
Physical Surface("CoilA", 2) = {{41}};
Physical Surface("CoilB", 3) = {{42}};
Physical Surface("Insert", 4) = {{43}};
Physical Curve("Boundary", 10) = {{1, 2, 3, 4}};
Physical Curve("Axis", 11) = {{4}};

// Near-axis refinement for stable field probing.
Field[1] = Box;
Field[1].VIn = hProbe;
Field[1].VOut = hFar;
Field[1].XMin = 0;
Field[1].XMax = {probe_rmax:.17g};
Field[1].YMin = {probe_y0:.17g};
Field[1].YMax = {probe_y1:.17g};
Field[1].Thickness = hFar;

// Resolve skin-depth-driven current diffusion inside and around the conductor.
Field[2] = Box;
Field[2].VIn = hInsert;
Field[2].VOut = hFar;
Field[2].XMin = {max(0.0, ir0 - insert_box_pad):.17g};
Field[2].XMax = {ir1 + insert_box_pad:.17g};
Field[2].YMin = {iy0 - insert_box_pad:.17g};
Field[2].YMax = {iy1 + insert_box_pad:.17g};
Field[2].Thickness = hFar;

Field[3] = Min;
Field[3].FieldsList = {{1, 2}};
Background Field = 3;

Mesh.MeshSizeFromPoints = 1;
// GetDP controls magnetic solution order; geometry remains linear.
Mesh.ElementOrder = 1;
Mesh.MshFileVersion = 2.2;
'''


def write_axisymmetric_gmsh_geo(config: POC005Config, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_axisymmetric_gmsh_geo(config), encoding="utf-8")
    return path
