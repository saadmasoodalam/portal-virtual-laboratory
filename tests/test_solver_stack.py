from pathlib import Path

import numpy as np
import pytest

from pvl.core.models import MeshConfig, POC001Config
from pvl.geometry.poc001 import write_gmsh_geo
from pvl.solvers.getdp.poc001_run import run_axisymmetric_poc001
from pvl.solvers.getdp.runner import (
    SolverUnavailableError,
    discover_executables,
    generate_mesh,
    solver_versions,
)
from pvl.validation.poc001 import analytical_reference


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


def test_poc001_getdp_magnetostatic_solve_produces_physical_axis_field(tmp_path: Path):
    exe = _solver_stack_or_skip()
    config = POC001Config(mesh=MeshConfig(characteristic_length_m=0.025, order=1))
    result = run_axisymmetric_poc001(config, tmp_path / "fem", executables=exe)
    reference = analytical_reference(config)

    assert result.mesh_file.exists()
    assert result.raw_axis_file.exists()
    assert np.all(np.isfinite(result.b_axis_t))
    assert np.all(result.b_axis_t > 0.0)

    # Keep detailed diagnostics in CI until the analytical-validation gate passes.
    print("PVL-POC-001 probe z [m]:", result.z_m)
    print("PVL-POC-001 FEM B_axis [T]:", result.b_axis_t)
    print("PVL-POC-001 analytic B_axis [T]:", reference.b_t)
    print("PVL-POC-001 ratio FEM/analytic:", result.b_axis_t / reference.b_t)
    print("PVL-POC-001 metrics:", result.metrics)
    print("PVL-POC-001 raw table head:\n", result.raw_axis_file.read_text(encoding="utf-8", errors="ignore")[:3000])

    # Initial integration gate. Do not relax this threshold to hide scaling/formulation errors.
    assert result.metrics["max_relative_error"] < 0.20
