import math

import pytest

from pvl.experiments.models import CoilDriveState, DriveMode, ExperimentConfig
from pvl.geometry.constructive import compile_constructive_topology
from pvl.geometry.exploratory import architecture_example_rig_v1
from pvl.geometry.gmsh_rig import RigGmshConfig, render_complete_rig_geo
from pvl.materials.library import load_builtin_material_library
from pvl.rig.fingerprint import rig_definition_fingerprint
from pvl.solvers.getdp.rig_magnetoquasistatic import (
    build_rig_magnetoquasistatic_model,
    render_rig_magnetoquasistatic_pro,
)


def _state(*, a_phase: float = 0.0, a_omega_sign: int = 1, b_phase: float = 0.0):
    rig = architecture_example_rig_v1()
    topology = compile_constructive_topology(rig)
    materials = load_builtin_material_library()
    _, manifest = render_complete_rig_geo(topology, RigGmshConfig(characteristic_length_m=0.04))
    experiment = ExperimentConfig(
        experiment_id="rig-mq-test",
        repetitions=1,
        material_library_fingerprint=materials.fingerprint_sha256(),
        rig_definition_fingerprint=rig_definition_fingerprint(rig),
        coil_a=CoilDriveState(
            mode=DriveMode.HARMONIC,
            current_a=1.0,
            polarity=1,
            frequency_hz=10.0,
            phase_rad=a_phase,
            omega_sign=a_omega_sign,
        ),
        coil_b=CoilDriveState(
            mode=DriveMode.HARMONIC,
            current_a=0.5,
            polarity=-1,
            frequency_hz=10.0,
            phase_rad=b_phase,
            omega_sign=1,
        ),
    )
    return rig, topology, materials, manifest, experiment


def test_complete_rig_mq_uses_common_frequency_phase_and_passive_conductors():
    _, topology, materials, manifest, experiment = _state(a_phase=0.25, b_phase=-0.4)
    model = build_rig_magnetoquasistatic_model(experiment, topology, manifest, materials)
    assert model.frequency_hz == pytest.approx(10.0)
    assert model.source_a.phase_rad == pytest.approx(0.25)
    assert model.source_b.phase_rad == pytest.approx(-0.4)
    assert model.source_a.spatial.ampere_turns == pytest.approx(500.0)
    assert model.source_b.spatial.ampere_turns == pytest.approx(-250.0)

    conductor_ids = {region.primitive_id for region in model.conductors}
    assert "winding:coil_a" not in conductor_ids
    assert "winding:coil_b" not in conductor_ids
    assert {"steel:north", "steel:south", "steel:east", "steel:west"}.issubset(conductor_ids)
    assert any(name.startswith("copper:") for name in conductor_ids)
    assert "sample:wall" in conductor_ids
    assert "sample:medium" not in conductor_ids  # default fixture is air


def test_negative_omega_is_only_canonical_positive_frequency_phase_mapping():
    _, topology_a, materials_a, manifest_a, exp_a = _state(a_phase=0.3, a_omega_sign=-1)
    model_a = build_rig_magnetoquasistatic_model(exp_a, topology_a, manifest_a, materials_a)
    assert model_a.source_a.phase_rad == pytest.approx(-0.3)

    _, topology_b, materials_b, manifest_b, exp_b = _state(a_phase=-0.3, a_omega_sign=1)
    model_b = build_rig_magnetoquasistatic_model(exp_b, topology_b, manifest_b, materials_b)
    assert model_b.source_a.phase_rad == pytest.approx(-0.3)


def test_complete_rig_mq_formulation_contains_only_established_harmonic_terms():
    _, topology, materials, manifest, experiment = _state()
    text = render_rig_magnetoquasistatic_pro(
        experiment,
        topology,
        manifest,
        materials,
        probe_y_m=(-0.03, 0.0, 0.03),
    )
    assert "Name Magnetoquasistatics_a_3D" in text
    assert "Type Complex; Frequency Freq" in text
    assert "DtDof [ sigma[] * Dof{a}, {a} ]" in text
    assert "In Vol_C_Mag" in text
    assert "In Vol_S_Mag" in text
    assert "F_Cos_wt_p" in text
    assert "0.5 * sigma[] * SquNorm[Dt[{a}]]" in text
    assert "JouleLosses" in text
    assert "CompY[{d a}]" in text
    assert "by_probe_re_001.txt" in text
    assert "biological model or Portal Hypothesis term is present" in text
    assert "F = F(" not in text
    assert "DeltaPsi" not in text


def test_complete_rig_mq_rejects_dc_and_mixed_frequency_states():
    rig, topology, materials, manifest, experiment = _state()
    dc = experiment.model_copy(
        update={"coil_a": CoilDriveState(mode=DriveMode.DC, current_a=1.0)}
    )
    with pytest.raises(ValueError, match="harmonic/OFF"):
        build_rig_magnetoquasistatic_model(dc, topology, manifest, materials)

    mismatched_b = CoilDriveState(
        mode=DriveMode.HARMONIC,
        current_a=1.0,
        frequency_hz=20.0,
    )
    mismatched = experiment.model_copy(update={"coil_b": mismatched_b})
    with pytest.raises(ValueError, match="common active frequency"):
        build_rig_magnetoquasistatic_model(mismatched, topology, manifest, materials)
