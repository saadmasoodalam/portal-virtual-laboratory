from pathlib import Path

import pytest

from pvl.core.models import POC001Config
from pvl.geometry.poc001 import write_gmsh_geo
from pvl.solvers.getdp.runner import (
    SolverUnavailableError,
    discover_executables,
    generate_mesh,
    solver_versions,
)


def _solver_stack_or_skip():
    try:
        return discover_executables()
    except SolverUnavailableError as exc:
        pytest.skip(str(exc))


def test_solver_versions_are_reported():
    exe = _solver_stack_or_skip()
    versions = solver_versions(exe)
    assert versions.gmsh != "unknown"
    assert versions.getdp != "unknown"


def test_poc001_geometry_generates_nonempty_3d_mesh(tmp_path: Path):
    exe = _solver_stack_or_skip()
    config = POC001Config()
    geo = write_gmsh_geo(config, tmp_path / "poc001.geo")
    mesh = generate_mesh(geo, dimension=3, executables=exe)

    assert mesh.exists()
    assert mesh.stat().st_size > 0
    text = mesh.read_text(encoding="utf-8", errors="ignore")
    assert "$MeshFormat" in text
    assert "$Nodes" in text
    assert "$Elements" in text
