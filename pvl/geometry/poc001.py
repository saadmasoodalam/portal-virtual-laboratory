from __future__ import annotations

from pathlib import Path

from pvl.core.models import POC001Config


def render_gmsh_geo(config: POC001Config) -> str:
    c = config.coil
    a = config.air
    h = config.mesh.characteristic_length_m
    return f'''// PVL-POC-001 generated geometry. SI units: metres.
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


def write_gmsh_geo(config: POC001Config, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_gmsh_geo(config), encoding="utf-8")
    return path
