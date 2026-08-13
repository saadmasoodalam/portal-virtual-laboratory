from __future__ import annotations

from pathlib import Path

from pvl.core.poc004_models import POC004Config


def render_gmsh_geo(config: POC004Config) -> str:
    """Render a uniform 2D conducting slab with driven left and grounded right A boundaries."""
    h = config.mesh.characteristic_length_m
    length = config.length_m
    half_height = config.height_m / 2.0
    return f'''// PVL-POC-004 conducting slab. SI units: metres.
// Cartesian 2D model: x is penetration depth; y is translationally uniform.
h = {h:.17g};
L = {length:.17g};
H2 = {half_height:.17g};

Point(1) = {{0, -H2, 0, h}};
Point(2) = {{L, -H2, 0, h}};
Point(3) = {{L, H2, 0, h}};
Point(4) = {{0, H2, 0, h}};
Line(1) = {{1, 2}};
Line(2) = {{2, 3}};
Line(3) = {{3, 4}};
Line(4) = {{4, 1}};
Curve Loop(10) = {{1, 2, 3, 4}};
Plane Surface(20) = {{10}};

Physical Surface("Conductor", 1) = {{20}};
Physical Curve("Right", 11) = {{2}};
Physical Curve("Left", 10) = {{4}};
Physical Curve("Bottom", 12) = {{1}};
Physical Curve("Top", 13) = {{3}};

Mesh.CharacteristicLengthMin = h;
Mesh.CharacteristicLengthMax = h;
// Keep geometry linear; GetDP controls magnetic approximation order.
Mesh.ElementOrder = 1;
Mesh.MshFileVersion = 2.2;
'''


def write_gmsh_geo(config: POC004Config, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_gmsh_geo(config), encoding="utf-8")
    return path
