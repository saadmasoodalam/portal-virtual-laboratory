from __future__ import annotations

import pytest

from pvl.experiments.models import (
    BoundaryCircuitState,
    ExperimentConfig,
    SampleMedium,
)
from pvl.geometry.exploratory import architecture_example_rig_v1
from pvl.materials.library import load_builtin_material_library
from pvl.rig.fingerprint import rig_definition_fingerprint
from pvl.sweeps.dc import DcSweepDefinition, NumericRange, plan_dc_sweep


def _base():
    rig = architecture_example_rig_v1()
    materials = load_builtin_material_library()
    experiment = ExperimentConfig(
        experiment_id="sweep-base",
        repetitions=1,
        material_library_fingerprint=materials.fingerprint_sha256(),
        rig_definition_fingerprint=rig_definition_fingerprint(rig),
    )
    return rig, materials, experiment


def test_example_current_grid_is_exactly_seventeen_states_and_three_media_make_867_points():
    rig, materials, experiment = _base()
    definition = DcSweepDefinition(
        sweep_id="example-867",
        coil_a_current_a=NumericRange(start=-2.0, stop=2.0, step=0.25),
        coil_b_current_a=NumericRange(start=-2.0, stop=2.0, step=0.25),
        media=(SampleMedium.AIR, SampleMedium.DISTILLED_WATER, SampleMedium.SALINE_0P9),
        copper_boundary_states=(BoundaryCircuitState.OPEN,),
    )
    assert len(definition.coil_a_current_a.values()) == 17
    assert definition.coil_a_current_a.values()[0] == -2.0
    assert definition.coil_a_current_a.values()[8] == 0.0
    assert definition.coil_a_current_a.values()[-1] == 2.0

    plan = plan_dc_sweep(
        definition,
        base_rig=rig,
        base_experiment=experiment,
        materials=materials,
    )
    assert plan.point_count == 17 * 17 * 3 == 867
    assert plan.solver_execution is False
    assert plan.hypothesis_analysis is False
    assert len({point.point_hash for point in plan.points}) == 867


def test_open_and_closed_copper_doubles_example_to_1734_and_changes_rig_fingerprint():
    rig, materials, experiment = _base()
    definition = DcSweepDefinition(
        sweep_id="example-1734",
        coil_a_current_a=NumericRange(start=-2.0, stop=2.0, step=0.25),
        coil_b_current_a=NumericRange(start=-2.0, stop=2.0, step=0.25),
        media=(SampleMedium.AIR, SampleMedium.DISTILLED_WATER, SampleMedium.SALINE_0P9),
        copper_boundary_states=(BoundaryCircuitState.OPEN, BoundaryCircuitState.CLOSED),
    )
    plan = plan_dc_sweep(definition, base_rig=rig, base_experiment=experiment, materials=materials)
    assert plan.point_count == 1734

    first_open = next(
        point for point in plan.points
        if point.signed_coil_a_current_a == -2.0
        and point.signed_coil_b_current_a == -2.0
        and point.medium == SampleMedium.AIR
        and point.copper_boundary_state == BoundaryCircuitState.OPEN
    )
    first_closed = next(
        point for point in plan.points
        if point.signed_coil_a_current_a == -2.0
        and point.signed_coil_b_current_a == -2.0
        and point.medium == SampleMedium.AIR
        and point.copper_boundary_state == BoundaryCircuitState.CLOSED
    )
    assert first_open.rig.copper_boundary.baseline_open_loop is True
    assert first_closed.rig.copper_boundary.baseline_open_loop is False
    assert first_open.rig_fingerprint != first_closed.rig_fingerprint
    assert first_open.experiment.rig_definition_fingerprint == first_open.rig_fingerprint
    assert first_closed.experiment.rig_definition_fingerprint == first_closed.rig_fingerprint


def test_medium_is_constructive_state_not_merely_an_experiment_label():
    rig, materials, experiment = _base()
    plan = plan_dc_sweep(
        DcSweepDefinition(
            sweep_id="medium-state",
            coil_a_current_a=NumericRange(start=0.0, stop=0.0, step=1.0),
            coil_b_current_a=NumericRange(start=0.0, stop=0.0, step=1.0),
            media=(SampleMedium.AIR, SampleMedium.DISTILLED_WATER, SampleMedium.SALINE_0P9),
        ),
        base_rig=rig,
        base_experiment=experiment,
        materials=materials,
    )
    assert [point.medium for point in plan.points] == [
        SampleMedium.AIR,
        SampleMedium.DISTILLED_WATER,
        SampleMedium.SALINE_0P9,
    ]
    assert [point.rig.sample_chamber.medium_material_id for point in plan.points] == [
        "air_baseline",
        "distilled_water_baseline",
        "saline_0p9_baseline",
    ]
    assert len({point.rig_fingerprint for point in plan.points}) == 3


def test_signed_current_maps_zero_to_off_and_negative_to_negative_polarity():
    rig, materials, experiment = _base()
    plan = plan_dc_sweep(
        DcSweepDefinition(
            sweep_id="signed-current",
            coil_a_current_a=NumericRange(start=-1.0, stop=1.0, step=1.0),
            coil_b_current_a=NumericRange(start=0.0, stop=0.0, step=1.0),
        ),
        base_rig=rig,
        base_experiment=experiment,
        materials=materials,
    )
    negative, zero, positive = plan.points
    assert negative.experiment.coil_a.mode.value == "dc"
    assert negative.experiment.coil_a.current_a == 1.0
    assert negative.experiment.coil_a.polarity == -1
    assert zero.experiment.coil_a.mode.value == "off"
    assert zero.experiment.coil_a.current_a == 0.0
    assert positive.experiment.coil_a.mode.value == "dc"
    assert positive.experiment.coil_a.current_a == 1.0
    assert positive.experiment.coil_a.polarity == 1


def test_sweep_plan_is_deterministic_for_identical_inputs():
    rig, materials, experiment = _base()
    definition = DcSweepDefinition(
        sweep_id="determinism",
        coil_a_current_a=NumericRange(start=-0.5, stop=0.5, step=0.5),
        coil_b_current_a=NumericRange(start=-0.5, stop=0.5, step=0.5),
        media=(SampleMedium.AIR, SampleMedium.SALINE_0P9),
        copper_boundary_states=(BoundaryCircuitState.OPEN, BoundaryCircuitState.CLOSED),
    )
    first = plan_dc_sweep(definition, base_rig=rig, base_experiment=experiment, materials=materials)
    second = plan_dc_sweep(definition, base_rig=rig, base_experiment=experiment, materials=materials)
    assert first == second
    assert first.sweep_hash == second.sweep_hash
    assert [point.point_hash for point in first.points] == [point.point_hash for point in second.points]


def test_cardinality_guard_rejects_sweep_before_solver_execution():
    rig, materials, experiment = _base()
    definition = DcSweepDefinition(
        sweep_id="too-large",
        coil_a_current_a=NumericRange(start=-2.0, stop=2.0, step=0.25),
        coil_b_current_a=NumericRange(start=-2.0, stop=2.0, step=0.25),
        media=(SampleMedium.AIR, SampleMedium.DISTILLED_WATER, SampleMedium.SALINE_0P9),
        copper_boundary_states=(BoundaryCircuitState.OPEN, BoundaryCircuitState.CLOSED),
        maximum_points=1000,
    )
    with pytest.raises(ValueError, match="1734 points"):
        plan_dc_sweep(definition, base_rig=rig, base_experiment=experiment, materials=materials)
