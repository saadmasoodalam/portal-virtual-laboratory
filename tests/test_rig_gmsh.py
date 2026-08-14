from __future__ import annotations

from math import sqrt
from pathlib import Path
import shutil

import pytest

from pvl.geometry.constructive import compile_constructive_topology
from pvl.geometry.exploratory import architecture_example_rig_v1
from pvl.geometry.gmsh_rig import RigGmshConfig, render_complete_rig_geo
from pvl.geometry.gmsh_rig_run import run_complete_rig_mesh
from pvl.geometry.msh2 import tetra_mean_ratio_quality, tetra_volume_m3


def test_equilateral_tetra_quality_is_one():
    points = (
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.5, sqrt(3.0) / 2.0, 0.0),
        (0.5, sqrt(3.0) / 6.0, sqrt(2.0 / 3.0)),
    )
    assert tetra_mean_ratio_quality(points) == pytest.approx(1.0, abs=1e-14)
    assert tetra_volume_m3(points) == pytest.approx(sqrt(2.0) / 12.0)


def test_complete_rig_geo_is_deterministic_and_contains_only_geometry_mesh_commands():
    topology = compile_constructive_topology(architecture_example_rig_v1())
    config = RigGmshConfig(characteristic_length_m=0.03)
    first, first_manifest = render_complete_rig_geo(topology, config)
    second, second_manifest = render_complete_rig_geo(topology, config)
    assert first == second
    assert first_manifest == second_manifest
    assert 'SetFactory("OpenCASCADE")' in first
    assert "BooleanFragments" in first
    assert 'Physical Volume("PVL_Air", 1)' in first
    assert "PVL_steel_north" in first
    assert "PVL_copper_east_south" in first
    assert "PVL_sample_wall" in first
    assert "PVL_winding_coil_a" in first
    assert "GetDP" in first  # only in the explicit no-solve scientific-boundary comment
    assert "Portal Hypothesis" in first  # only in the explicit exclusion comment
    assert "Resolution" not in first
    assert "Formulation" not in first


def test_air_box_strictly_contains_every_material_primitive():
    topology = compile_constructive_topology(architecture_example_rig_v1())
    _, manifest = render_complete_rig_geo(topology, RigGmshConfig())
    xmin, xmax, ymin, ymax, zmin, zmax = manifest.air_bounds_m
    for primitive in topology.primitives:
        if primitive.material_id is None:
            continue
        from pvl.geometry.gmsh_rig import primitive_bounds

        px0, px1, py0, py1, pz0, pz1 = primitive_bounds(primitive)
        assert xmin < px0 <= px1 < xmax
        assert ymin < py0 <= py1 < ymax
        assert zmin < pz0 <= pz1 < zmax


def test_complete_rig_mesh_smoke_gate_when_gmsh_is_available(tmp_path: Path):
    gmsh = shutil.which("gmsh")
    if gmsh is None:
        pytest.skip("Gmsh executable not installed")
    topology = compile_constructive_topology(architecture_example_rig_v1())
    result = run_complete_rig_mesh(
        topology,
        RigGmshConfig(characteristic_length_m=0.035, minimum_characteristic_length_m=0.001),
        tmp_path,
        gmsh_executable=gmsh,
    )
    assert result.gate.passed, result.gate.model_dump(mode="json")
    assert result.summary.tetrahedron_count > 0
    assert result.summary.minimum_tetra_volume_m3 > 0.0
    assert result.summary.minimum_mean_ratio_quality >= 0.01
    assert set(result.summary.physical_names.values()) == set(result.gmsh_manifest.required_physical_names)
    assert not (tmp_path / "solver_input.pro").exists()
    assert not (tmp_path / "fields.vtu").exists()
    assert not (tmp_path / "getdp_stdout.log").exists()
