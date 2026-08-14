from __future__ import annotations

from math import sqrt
from pathlib import Path

from pydantic import Field

from pvl.core.models import FrozenModel


class Msh2TetraSummary(FrozenModel):
    node_count: int = Field(ge=0)
    element_count: int = Field(ge=0)
    tetrahedron_count: int = Field(ge=0)
    physical_names: dict[int, str]
    tetrahedra_by_physical_tag: dict[int, int]
    minimum_tetra_volume_m3: float = Field(ge=0.0)
    maximum_tetra_volume_m3: float = Field(ge=0.0)
    minimum_mean_ratio_quality: float = Field(ge=0.0)
    mean_mean_ratio_quality: float = Field(ge=0.0)

    @property
    def tetrahedra_by_physical_name(self) -> dict[str, int]:
        return {
            self.physical_names[tag]: count
            for tag, count in self.tetrahedra_by_physical_tag.items()
            if tag in self.physical_names
        }


def _section(lines: list[str], start: str, end: str) -> list[str]:
    try:
        i = lines.index(start)
        j = lines.index(end, i + 1)
    except ValueError as exc:
        raise ValueError(f"MSH2 section missing: {start}") from exc
    return lines[i + 1 : j]


def _parse_physical_names(lines: list[str]) -> dict[int, str]:
    if "$PhysicalNames" not in lines:
        return {}
    section = _section(lines, "$PhysicalNames", "$EndPhysicalNames")
    if not section:
        return {}
    expected = int(section[0])
    result: dict[int, str] = {}
    for row in section[1:]:
        parts = row.split(maxsplit=2)
        if len(parts) != 3:
            raise ValueError(f"invalid MSH2 physical-name row: {row}")
        dimension, tag = int(parts[0]), int(parts[1])
        if dimension != 3:
            continue
        name = parts[2].strip()
        if len(name) < 2 or name[0] != '"' or name[-1] != '"':
            raise ValueError(f"invalid quoted MSH2 physical name: {row}")
        result[tag] = name[1:-1]
    # The declared count includes lower-dimensional groups if present.
    if expected < len(result):
        raise ValueError("MSH2 physical-name count is inconsistent")
    return result


def _parse_nodes(lines: list[str]) -> dict[int, tuple[float, float, float]]:
    section = _section(lines, "$Nodes", "$EndNodes")
    if not section:
        raise ValueError("MSH2 node section is empty")
    expected = int(section[0])
    nodes: dict[int, tuple[float, float, float]] = {}
    for row in section[1:]:
        values = row.split()
        if len(values) != 4:
            raise ValueError(f"invalid MSH2 node row: {row}")
        tag = int(values[0])
        nodes[tag] = (float(values[1]), float(values[2]), float(values[3]))
    if len(nodes) != expected:
        raise ValueError(f"MSH2 node count mismatch: expected {expected}, parsed {len(nodes)}")
    return nodes


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def tetra_volume_m3(points: tuple[tuple[float, float, float], ...]) -> float:
    a = _sub(points[1], points[0])
    b = _sub(points[2], points[0])
    c = _sub(points[3], points[0])
    return abs(_dot(a, _cross(b, c))) / 6.0


def tetra_mean_ratio_quality(points: tuple[tuple[float, float, float], ...]) -> float:
    """Return the tetrahedral mean-ratio quality in [0, 1] for valid straight tets.

    q = 12 (3 V)^(2/3) / sum_{six edges}(l^2), with q=1 for an equilateral tetrahedron.
    This is a PVL mesh-health metric, not a claim of equivalence to a named Gmsh API metric.
    """
    volume = tetra_volume_m3(points)
    if volume <= 0.0:
        return 0.0
    edges = ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))
    squared_sum = 0.0
    for i, j in edges:
        delta = _sub(points[i], points[j])
        squared_sum += _dot(delta, delta)
    if squared_sum <= 0.0:
        return 0.0
    value = 12.0 * (3.0 * volume) ** (2.0 / 3.0) / squared_sum
    # Round-off can put a near-equilateral element infinitesimally above one.
    return min(1.0, max(0.0, value))


def parse_msh2_tetra_summary(path: Path) -> Msh2TetraSummary:
    lines = [line.strip() for line in path.read_text(encoding="utf-8", errors="strict").splitlines()]
    if "$MeshFormat" not in lines:
        raise ValueError("not a Gmsh mesh")
    mesh_format = _section(lines, "$MeshFormat", "$EndMeshFormat")
    if not mesh_format or not mesh_format[0].startswith("2.2 "):
        raise ValueError("PVL-2P parser requires ASCII MSH 2.2")

    physical_names = _parse_physical_names(lines)
    nodes = _parse_nodes(lines)
    section = _section(lines, "$Elements", "$EndElements")
    if not section:
        raise ValueError("MSH2 element section is empty")
    expected_elements = int(section[0])
    tetra_counts: dict[int, int] = {}
    volumes: list[float] = []
    qualities: list[float] = []

    for row in section[1:]:
        values = row.split()
        if len(values) < 3:
            raise ValueError(f"invalid MSH2 element row: {row}")
        element_type = int(values[1])
        number_of_tags = int(values[2])
        first_node = 3 + number_of_tags
        if element_type != 4:
            continue
        if len(values) != first_node + 4:
            raise ValueError(f"invalid linear-tetra MSH2 row: {row}")
        if number_of_tags < 1:
            raise ValueError("tetrahedron has no physical tag")
        physical_tag = int(values[3])
        node_tags = tuple(int(value) for value in values[first_node : first_node + 4])
        try:
            points = tuple(nodes[tag] for tag in node_tags)
        except KeyError as exc:
            raise ValueError(f"tetrahedron references missing node {exc.args[0]}") from exc
        volume = tetra_volume_m3(points)
        quality = tetra_mean_ratio_quality(points)
        tetra_counts[physical_tag] = tetra_counts.get(physical_tag, 0) + 1
        volumes.append(volume)
        qualities.append(quality)

    parsed_elements = len(section) - 1
    if parsed_elements != expected_elements:
        raise ValueError(
            f"MSH2 element count mismatch: expected {expected_elements}, parsed {parsed_elements}"
        )
    if not volumes:
        raise ValueError("mesh contains no first-order tetrahedra")
    return Msh2TetraSummary(
        node_count=len(nodes),
        element_count=expected_elements,
        tetrahedron_count=len(volumes),
        physical_names=physical_names,
        tetrahedra_by_physical_tag=tetra_counts,
        minimum_tetra_volume_m3=min(volumes),
        maximum_tetra_volume_m3=max(volumes),
        minimum_mean_ratio_quality=min(qualities),
        mean_mean_ratio_quality=sum(qualities) / len(qualities),
    )
