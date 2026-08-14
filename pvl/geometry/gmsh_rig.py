from __future__ import annotations

from math import sqrt
from pathlib import Path
import re

from pydantic import Field, model_validator

from pvl.core.models import FrozenModel
from pvl.geometry.constructive import (
    ConstructivePrimitive,
    ConstructivePrimitiveKind,
    RigConstructiveTopology,
)


RIG_GMSH_SCHEMA_VERSION = "pvl-rig-gmsh-v2"
AIR_VOLUME_TAG = 900
AIR_SOURCE_TAG = 9000
AIR_PHYSICAL_TAG = 1
OUTER_BOUNDARY_PHYSICAL_TAG = 5000


class RigGmshConfig(FrozenModel):
    characteristic_length_m: float = Field(default=0.025, gt=0.0)
    minimum_characteristic_length_m: float = Field(default=0.001, gt=0.0)
    air_margin_fraction: float = Field(default=0.35, gt=0.0)
    air_min_margin_m: float = Field(default=0.05, gt=0.0)
    msh_version: str = "2.2"

    @model_validator(mode="after")
    def mesh_size_order(self) -> "RigGmshConfig":
        if self.minimum_characteristic_length_m > self.characteristic_length_m:
            raise ValueError("minimum characteristic length cannot exceed global characteristic length")
        if self.msh_version != "2.2":
            raise ValueError("PVL currently validates only MSH 2.2 output")
        return self


class RigPhysicalRegion(FrozenModel):
    primitive_id: str
    physical_name: str
    physical_tag: int = Field(gt=0)
    volume_tag: int = Field(gt=0)
    material_id: str | None


class RigGmshManifest(FrozenModel):
    schema_version: str = RIG_GMSH_SCHEMA_VERSION
    rig_id: str
    source_rig_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    constructive_topology_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    gmsh_configuration_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    geometry_fidelity: str = "exploratory_complete_rig_mesh"
    solver_execution: bool = False
    air_physical_name: str = "PVL_Air"
    air_physical_tag: int = AIR_PHYSICAL_TAG
    air_volume_tag: int = AIR_VOLUME_TAG
    outer_boundary_physical_name: str = "PVL_OuterBoundary"
    outer_boundary_physical_tag: int = OUTER_BOUNDARY_PHYSICAL_TAG
    air_bounds_m: tuple[float, float, float, float, float, float]
    physical_regions: tuple[RigPhysicalRegion, ...]

    @property
    def required_physical_names(self) -> tuple[str, ...]:
        """Required 3D physical-volume names; the outer boundary is a 2D physical group."""
        return (self.air_physical_name,) + tuple(region.physical_name for region in self.physical_regions)


def _fmt(value: float) -> str:
    return f"{value:.17g}"


def _physical_name(primitive_id: str) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "_", primitive_id).strip("_")
    return "PVL_" + value


def _axis_extent(axis: tuple[float, float, float], axial_half: float, radial: float) -> tuple[float, float, float]:
    return tuple(
        axial_half * abs(component) + radial * sqrt(max(0.0, 1.0 - component * component))
        for component in axis
    )


def primitive_bounds(primitive: ConstructivePrimitive) -> tuple[float, float, float, float, float, float]:
    cx, cy, cz = primitive.center_m
    if primitive.kind == ConstructivePrimitiveKind.BOX:
        if primitive.size_m is None:
            raise ValueError(f"box primitive has no size: {primitive.primitive_id}")
        ex, ey, ez = (value / 2.0 for value in primitive.size_m)
    elif primitive.kind in {ConstructivePrimitiveKind.CYLINDRICAL_SHELL, ConstructivePrimitiveKind.CYLINDRICAL_VOLUME}:
        if primitive.axis is None:
            raise ValueError(f"cylindrical primitive has no axis: {primitive.primitive_id}")
        radius = primitive.parameters_m.get("outer_radius", primitive.parameters_m.get("radius"))
        height = primitive.parameters_m.get("height")
        if radius is None or height is None:
            raise ValueError(f"cylindrical primitive parameters incomplete: {primitive.primitive_id}")
        ex, ey, ez = _axis_extent(primitive.axis, height / 2.0, radius)
    elif primitive.kind == ConstructivePrimitiveKind.WINDING_ENVELOPE:
        if primitive.axis is None:
            raise ValueError(f"winding primitive has no axis: {primitive.primitive_id}")
        mean = primitive.parameters_m["mean_radius"]
        radial = primitive.parameters_m["radial_thickness"]
        axial = primitive.parameters_m["axial_length"]
        ex, ey, ez = _axis_extent(primitive.axis, axial / 2.0, mean + radial / 2.0)
    elif primitive.kind == ConstructivePrimitiveKind.PROBE_POINT:
        ex = ey = ez = 0.0
    else:
        raise ValueError(f"unsupported constructive primitive: {primitive.kind}")
    return (cx - ex, cx + ex, cy - ey, cy + ey, cz - ez, cz + ez)


def topology_air_bounds(
    topology: RigConstructiveTopology,
    config: RigGmshConfig,
) -> tuple[float, float, float, float, float, float]:
    material = [p for p in topology.primitives if p.kind != ConstructivePrimitiveKind.PROBE_POINT]
    if not material:
        raise ValueError("constructive topology has no material primitives")
    bounds = [primitive_bounds(p) for p in material]
    minimum = [min(item[axis * 2] for item in bounds) for axis in range(3)]
    maximum = [max(item[axis * 2 + 1] for item in bounds) for axis in range(3)]
    size = [maximum[i] - minimum[i] for i in range(3)]
    pad = [max(size[i] * config.air_margin_fraction, config.air_min_margin_m) for i in range(3)]
    return (
        minimum[0] - pad[0],
        maximum[0] + pad[0],
        minimum[1] - pad[1],
        maximum[1] + pad[1],
        minimum[2] - pad[2],
        maximum[2] + pad[2],
    )


def _start_and_vector(
    center: tuple[float, float, float],
    axis: tuple[float, float, float],
    length: float,
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    vector = tuple(component * length for component in axis)
    start = tuple(center[i] - vector[i] / 2.0 for i in range(3))
    return start, vector


def _render_primitive(primitive: ConstructivePrimitive, volume_tag: int) -> list[str]:
    lines: list[str] = [f"// {primitive.primitive_id}"]
    if primitive.kind == ConstructivePrimitiveKind.BOX:
        if primitive.size_m is None:
            raise ValueError(f"box primitive has no size: {primitive.primitive_id}")
        start = tuple(primitive.center_m[i] - primitive.size_m[i] / 2.0 for i in range(3))
        lines.append(
            f"Box({volume_tag}) = {{{_fmt(start[0])}, {_fmt(start[1])}, {_fmt(start[2])}, "
            f"{_fmt(primitive.size_m[0])}, {_fmt(primitive.size_m[1])}, {_fmt(primitive.size_m[2])}}};"
        )
        return lines

    if primitive.kind == ConstructivePrimitiveKind.CYLINDRICAL_VOLUME:
        if primitive.axis is None:
            raise ValueError(f"cylindrical primitive has no axis: {primitive.primitive_id}")
        radius = primitive.parameters_m["radius"]
        height = primitive.parameters_m["height"]
        start, vector = _start_and_vector(primitive.center_m, primitive.axis, height)
        lines.append(
            f"Cylinder({volume_tag}) = {{{_fmt(start[0])}, {_fmt(start[1])}, {_fmt(start[2])}, "
            f"{_fmt(vector[0])}, {_fmt(vector[1])}, {_fmt(vector[2])}, {_fmt(radius)}}};"
        )
        return lines

    if primitive.kind == ConstructivePrimitiveKind.CYLINDRICAL_SHELL:
        if primitive.axis is None:
            raise ValueError(f"shell primitive has no axis: {primitive.primitive_id}")
        outer = primitive.parameters_m["outer_radius"]
        wall = primitive.parameters_m["wall_thickness"]
        height = primitive.parameters_m["height"]
        inner = outer - wall
        if inner <= 0.0:
            raise ValueError(f"shell inner radius is not positive: {primitive.primitive_id}")
        start, vector = _start_and_vector(primitive.center_m, primitive.axis, height)
        outer_tag = volume_tag + 1
        inner_tag = volume_tag + 2
        lines.extend([
            f"Cylinder({outer_tag}) = {{{_fmt(start[0])}, {_fmt(start[1])}, {_fmt(start[2])}, {_fmt(vector[0])}, {_fmt(vector[1])}, {_fmt(vector[2])}, {_fmt(outer)}}};",
            f"Cylinder({inner_tag}) = {{{_fmt(start[0])}, {_fmt(start[1])}, {_fmt(start[2])}, {_fmt(vector[0])}, {_fmt(vector[1])}, {_fmt(vector[2])}, {_fmt(inner)}}};",
            f"BooleanDifference({volume_tag}) = {{ Volume{{{outer_tag}}}; Delete; }}{{ Volume{{{inner_tag}}}; Delete; }};",
        ])
        return lines

    if primitive.kind == ConstructivePrimitiveKind.WINDING_ENVELOPE:
        if primitive.axis is None:
            raise ValueError(f"winding primitive has no axis: {primitive.primitive_id}")
        mean = primitive.parameters_m["mean_radius"]
        radial = primitive.parameters_m["radial_thickness"]
        length = primitive.parameters_m["axial_length"]
        outer = mean + radial / 2.0
        inner = mean - radial / 2.0
        if inner <= 0.0:
            raise ValueError(f"winding inner radius is not positive: {primitive.primitive_id}")
        start, vector = _start_and_vector(primitive.center_m, primitive.axis, length)
        outer_tag = volume_tag + 1
        inner_tag = volume_tag + 2
        lines.extend([
            f"Cylinder({outer_tag}) = {{{_fmt(start[0])}, {_fmt(start[1])}, {_fmt(start[2])}, {_fmt(vector[0])}, {_fmt(vector[1])}, {_fmt(vector[2])}, {_fmt(outer)}}};",
            f"Cylinder({inner_tag}) = {{{_fmt(start[0])}, {_fmt(start[1])}, {_fmt(start[2])}, {_fmt(vector[0])}, {_fmt(vector[1])}, {_fmt(vector[2])}, {_fmt(inner)}}};",
            f"BooleanDifference({volume_tag}) = {{ Volume{{{outer_tag}}}; Delete; }}{{ Volume{{{inner_tag}}}; Delete; }};",
        ])
        return lines

    if primitive.kind == ConstructivePrimitiveKind.PROBE_POINT:
        return lines
    raise ValueError(f"unsupported constructive primitive: {primitive.kind}")


def build_gmsh_manifest(topology: RigConstructiveTopology, config: RigGmshConfig) -> RigGmshManifest:
    regions: list[RigPhysicalRegion] = []
    material_index = 0
    for primitive in topology.primitives:
        if primitive.kind == ConstructivePrimitiveKind.PROBE_POINT:
            continue
        volume_tag = 100 + material_index * 10
        regions.append(
            RigPhysicalRegion(
                primitive_id=primitive.primitive_id,
                physical_name=_physical_name(primitive.primitive_id),
                physical_tag=100 + material_index,
                volume_tag=volume_tag,
                material_id=primitive.material_id,
            )
        )
        material_index += 1
    return RigGmshManifest(
        rig_id=topology.rig_id,
        source_rig_fingerprint=topology.source_rig_fingerprint,
        constructive_topology_fingerprint=topology.fingerprint_sha256(),
        gmsh_configuration_hash=config.configuration_hash(),
        air_bounds_m=topology_air_bounds(topology, config),
        physical_regions=tuple(regions),
    )


def render_complete_rig_geo(topology: RigConstructiveTopology, config: RigGmshConfig) -> tuple[str, RigGmshManifest]:
    manifest = build_gmsh_manifest(topology, config)
    lines = [
        "// PVL complete-Rig exploratory Gmsh geometry.",
        "// Ordinary geometry/meshing only. No GetDP solve and no Portal Hypothesis term.",
        'SetFactory("OpenCASCADE");',
        "Geometry.OCCBooleanPreserveNumbering = 1;",
        f"Mesh.MshFileVersion = {config.msh_version};",
        "Mesh.ElementOrder = 1;",
        f"Mesh.CharacteristicLengthMin = {_fmt(config.minimum_characteristic_length_m)};",
        f"Mesh.CharacteristicLengthMax = {_fmt(config.characteristic_length_m)};",
        "Mesh.MeshSizeFromCurvature = 0;",
        "Mesh.MeshSizeExtendFromBoundary = 1;",
        "",
    ]

    region_by_id = {region.primitive_id: region for region in manifest.physical_regions}
    for primitive in topology.primitives:
        if primitive.kind == ConstructivePrimitiveKind.PROBE_POINT:
            continue
        lines.extend(_render_primitive(primitive, region_by_id[primitive.primitive_id].volume_tag))
        lines.append("")

    xmin, xmax, ymin, ymax, zmin, zmax = manifest.air_bounds_m
    volume_tags = ",".join(str(region.volume_tag) for region in manifest.physical_regions)
    extent = max(xmax - xmin, ymax - ymin, zmax - zmin)
    # OpenCASCADE entity bounding boxes include kernel tolerances. Keep this selection slab much
    # wider than that numerical fuzz while remaining orders of magnitude inside the retained
    # >=50 mm air padding, so internal material interfaces cannot be selected.
    boundary_eps = max(1e-6, extent * 1e-5)
    lines.extend([
        "// Surrounding air before conformal fragmentation.",
        f"Box({AIR_SOURCE_TAG}) = {{{_fmt(xmin)}, {_fmt(ymin)}, {_fmt(zmin)}, {_fmt(xmax - xmin)}, {_fmt(ymax - ymin)}, {_fmt(zmax - zmin)}}};",
        f"BooleanDifference({AIR_VOLUME_TAG}) = {{ Volume{{{AIR_SOURCE_TAG}}}; Delete; }}{{ Volume{{{volume_tags}}}; }};",
        "",
        "// Fragment retained material volumes against the air cavity interfaces so later FEM",
        "// formulations see one conformal topological model. OCC numbering preservation is",
        "// validated by PVL's physical-region mesh gate.",
        f"allFragments() = BooleanFragments{{ Volume{{{AIR_VOLUME_TAG}}}; Delete; }}{{ Volume{{{volume_tags}}}; Delete; }};",
        "",
        "// PVL-2Q identifies only the six external faces of the padded air box. Material",
        "// interfaces cannot enter these bounding slabs because all material primitives are",
        "// strictly contained by the air padding and were checked by PVL-2P.",
        f"bndEps = {_fmt(boundary_eps)};",
        "outerBnd() = {};",
        f"outerBnd() += Surface In BoundingBox{{{_fmt(xmin - boundary_eps)}, {_fmt(ymin - boundary_eps)}, {_fmt(zmin - boundary_eps)}, {_fmt(xmin + boundary_eps)}, {_fmt(ymax + boundary_eps)}, {_fmt(zmax + boundary_eps)}}};",
        f"outerBnd() += Surface In BoundingBox{{{_fmt(xmax - boundary_eps)}, {_fmt(ymin - boundary_eps)}, {_fmt(zmin - boundary_eps)}, {_fmt(xmax + boundary_eps)}, {_fmt(ymax + boundary_eps)}, {_fmt(zmax + boundary_eps)}}};",
        f"outerBnd() += Surface In BoundingBox{{{_fmt(xmin - boundary_eps)}, {_fmt(ymin - boundary_eps)}, {_fmt(zmin - boundary_eps)}, {_fmt(xmax + boundary_eps)}, {_fmt(ymin + boundary_eps)}, {_fmt(zmax + boundary_eps)}}};",
        f"outerBnd() += Surface In BoundingBox{{{_fmt(xmin - boundary_eps)}, {_fmt(ymax - boundary_eps)}, {_fmt(zmin - boundary_eps)}, {_fmt(xmax + boundary_eps)}, {_fmt(ymax + boundary_eps)}, {_fmt(zmax + boundary_eps)}}};",
        f"outerBnd() += Surface In BoundingBox{{{_fmt(xmin - boundary_eps)}, {_fmt(ymin - boundary_eps)}, {_fmt(zmin - boundary_eps)}, {_fmt(xmax + boundary_eps)}, {_fmt(ymax + boundary_eps)}, {_fmt(zmin + boundary_eps)}}};",
        f"outerBnd() += Surface In BoundingBox{{{_fmt(xmin - boundary_eps)}, {_fmt(ymin - boundary_eps)}, {_fmt(zmax - boundary_eps)}, {_fmt(xmax + boundary_eps)}, {_fmt(ymax + boundary_eps)}, {_fmt(zmax + boundary_eps)}}};",
        "",
        f'Physical Volume("{manifest.air_physical_name}", {manifest.air_physical_tag}) = {{{manifest.air_volume_tag}}};',
    ])
    for region in manifest.physical_regions:
        lines.append(
            f'Physical Volume("{region.physical_name}", {region.physical_tag}) = {{{region.volume_tag}}};'
        )
    lines.extend([
        f'Physical Surface("{manifest.outer_boundary_physical_name}", {manifest.outer_boundary_physical_tag}) = {{outerBnd()}};',
        "",
        "// MSH2 stores physical membership used by PVL's independent integrity parsers.",
        "Mesh.SaveAll = 0;",
        "Mesh.Optimize = 1;",
        "",
    ])
    return "\n".join(lines), manifest


def write_complete_rig_geo(
    topology: RigConstructiveTopology,
    config: RigGmshConfig,
    path: Path,
) -> tuple[Path, RigGmshManifest]:
    text, manifest = render_complete_rig_geo(topology, config)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path, manifest
