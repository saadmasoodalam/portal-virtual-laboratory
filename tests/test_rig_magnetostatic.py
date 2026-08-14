from __future__ import annotations

import math

import pytest

from pvl.experiments.models import CoilDriveState, DriveMode, ExperimentConfig
from pvl.geometry.constructive import compile_constructive_topology
from pvl.geometry.exploratory import architecture_example_rig_v1
from pvl.geometry.gmsh_rig import RigGmshConfig, render_complete_rig_geo
from pvl.materials.library import load_builtin_material_library
from pvl.rig.fingerprint import rig_definition_fingerprint
from pvl.solvers.getdp.rig_magnetostatic import (
    build_winding_sources,
    render_rig_magnetostatic_pro,
)


def _state(*, a_current: float = 1.0, a_polarity: int = 1, b_current: float = 0.0, b_polarity: int = 1):
    rig = architecture_example_rig_v1()
    topology = compile_constructive_topology(rig)
    materials = load_builtin_material_library()
    _, manifest = render_complete_rig_geo(topology, RigGmshConfig())
    coil_a = (
        CoilDriveState(mode=DriveMode.DC, current_a=a_current, polarity=a_polarity)
        if a_current > 0.0
        else CoilDriveState()
    )
    coil_b = (
        CoilDriveState(mode=DriveMode.DC, current_a=b_current, polarity=b_polarity)
        if b_current > 0.0
        else CoilDriveState()
    )
    experiment = ExperimentConfig(
        experiment_id="rig-magnetostatic-test",
        repetitions=1,
        material_library_fingerprint=materials.fingerprint_sha256(),
        rig_definition_fingerprint=rig_definition_fingerprint(rig),
        coil_a=coil_a,
        coil_b=coil_b,
    )
    return rig, topology, materials, manifest, experiment


def test_gmsh_geometry_exposes_six_face_outer_boundary_physical_group():
    _, topology, _, _, _ = _state()
    text, manifest = render_complete_rig_geo(topology, RigGmshConfig())
    assert text.count("Surface In BoundingBox") == 6
    assert f'Physical Surface("{manifest.outer_boundary_physical_name}", {manifest.outer_boundary_physical_tag})' in text
    assert manifest.outer_boundary_physical_name == "PVL_OuterBoundary"
    assert manifest.outer_boundary_physical_tag == 5000


def test_complete_rig_local_mesh_controls_must_refine_not_coarsen_global_mesh():
    with pytest.raises(ValueError, match="must refine, not coarsen"):
        RigGmshConfig(
            characteristic_length_m=0.012,
            winding_characteristic_length_m=0.020,
        )


def test_complete_rig_geometry_emits_explicit_winding_and_steel_local_mesh_targets():
    _, topology, _, _, _ = _state()
    text, _ = render_complete_rig_geo(
        topology,
        RigGmshConfig(
            characteristic_length_m=0.012,
            winding_characteristic_length_m=0.002,
            steel_characteristic_length_m=0.005,
        ),
    )
    assert "Mesh.MeshSizeFromPoints = 1;" in text
    assert "Local target mesh size on winding envelopes" in text
    assert "Local target mesh size on steel frame" in text
    assert "= 0.002;" in text
    assert "= 0.0050000000000000001;" in text or "= 0.005;" in text
    assert text.count("MeshSize{ PointsOf{ Volume{") == 2


def test_homogenized_winding_source_integrates_to_ampere_turns_without_double_counting_turns():
    _, topology, _, manifest, experiment = _state(a_current=1.0)
    source_a, source_b = build_winding_sources(experiment, topology, manifest)
    assert source_a.turns == 500
    assert source_a.pack_cross_section_m2 == pytest.approx(0.006 * 0.010)
    assert source_a.ampere_turns == pytest.approx(500.0)
    assert source_a.integrated_cross_section_current_a == pytest.approx(500.0)
    assert source_a.current_density_a_m2 == pytest.approx(500.0 / (0.006 * 0.010))
    assert source_b.ampere_turns == 0.0
    assert source_b.current_density_a_m2 == 0.0


def test_electrical_reference_is_global_positive_y_not_opposite_geometric_normal_signs():
    _, topology, _, manifest, experiment = _state(a_current=1.0, b_current=1.0)
    source_a, source_b = build_winding_sources(experiment, topology, manifest)
    assert source_a.geometric_axis_y_sign == 1
    assert source_b.geometric_axis_y_sign == -1
    assert source_a.electrical_reference_y_sign == 1
    assert source_b.electrical_reference_y_sign == 1
    assert source_a.ampere_turns == source_b.ampere_turns == 500.0


def test_negative_experiment_polarity_flips_source_amplitude_only():
    _, topology, _, manifest, experiment = _state(a_current=1.0, a_polarity=-1)
    source_a, _ = build_winding_sources(experiment, topology, manifest)
    assert source_a.ampere_turns == -500.0
    assert source_a.integrated_cross_section_current_a == pytest.approx(-500.0)
    assert source_a.electrical_reference_y_sign == 1


def test_complete_rig_getdp_formulation_uses_3d_hcurl_tree_cotree_and_linear_material_mu():
    _, topology, materials, manifest, experiment = _state(a_current=1.0)
    text = render_rig_magnetostatic_pro(experiment, topology, manifest, materials)
    assert "Type Form1" in text
    assert "Function BF_Edge" in text
    assert "EdgesOfTreeIn" in text
    assert "EntitySubType StartingOn" in text
    assert "SubRegion Bnd" in text
    assert "nu[R_steel_north] = 1. / (mu0 * (100" in text
    assert "Integral { [ nu[] * Dof{d a}, {d a} ]" in text
    assert "Integral { [ -js[], {a} ]" in text
    assert "Joule" not in text
    assert "DtDof" not in text
    assert "Type Complex" not in text


def test_source_expression_has_no_axis_singularity_inside_winding_pack():
    _, topology, _, manifest, experiment = _state(a_current=1.0)
    source_a, _ = build_winding_sources(experiment, topology, manifest)
    winding = next(item for item in topology.primitives if item.primitive_id == "winding:coil_a")
    inner_radius = winding.parameters_m["mean_radius"] - winding.parameters_m["radial_thickness"] / 2.0
    assert inner_radius > 0.0
    assert math.isfinite(source_a.current_density_a_m2)
