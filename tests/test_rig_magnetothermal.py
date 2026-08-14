import pytest

from pvl.experiments.models import CoilDriveState, DriveMode, ExperimentConfig
from pvl.geometry.constructive import compile_constructive_topology
from pvl.geometry.exploratory import architecture_example_rig_v1
from pvl.geometry.gmsh_rig import RigGmshConfig, render_complete_rig_geo
from pvl.materials.library import load_builtin_material_library
from pvl.rig.fingerprint import rig_definition_fingerprint
from pvl.solvers.getdp.rig_magnetothermal import render_rig_magnetothermal_pro


def _state():
    rig = architecture_example_rig_v1()
    topology = compile_constructive_topology(rig)
    materials = load_builtin_material_library()
    _, manifest = render_complete_rig_geo(
        topology,
        RigGmshConfig(characteristic_length_m=0.04),
    )
    experiment = ExperimentConfig(
        experiment_id="rig-magthe-test",
        repetitions=1,
        material_library_fingerprint=materials.fingerprint_sha256(),
        rig_definition_fingerprint=rig_definition_fingerprint(rig),
        coil_a=CoilDriveState(
            mode=DriveMode.HARMONIC,
            current_a=0.2,
            frequency_hz=10.0,
            phase_rad=0.0,
        ),
        coil_b=CoilDriveState(),
    )
    return topology, materials, manifest, experiment


def test_magnetothermal_formulation_uses_joule_source_and_explicit_thermal_conductivity():
    topology, materials, manifest, experiment = _state()
    text = render_rig_magnetothermal_pro(
        experiment,
        topology,
        manifest,
        materials,
        ambient_temperature_k=293.15,
        probe_y_m=(-0.03, 0.0, 0.03),
    )
    assert "Name Thermal_Joule_3D" in text
    assert "Name MagThe" in text
    assert "Name H1_T_The; Type Form0" in text
    assert "k_The[Region[1]] = 0.0257" in text
    assert "0.5 * sigma[] * <a>[SquNorm[Dt[{a}]]]" in text
    assert "Region Bnd_The; Value T_ambient" in text
    assert "Name ThermalDiagnostics" in text
    assert "temperature_axis.txt" in text
    assert "thermal_joule_input.txt" in text
    assert "No unvalidated convection coefficient is hidden" in text
    assert "Portal Hypothesis" in text  # explicit exclusion comment only


def test_magnetothermal_rejects_invalid_ambient_temperature():
    topology, materials, manifest, experiment = _state()
    with pytest.raises(ValueError, match="ambient"):
        render_rig_magnetothermal_pro(
            experiment,
            topology,
            manifest,
            materials,
            ambient_temperature_k=0.0,
        )
