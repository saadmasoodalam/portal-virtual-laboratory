from __future__ import annotations

import pytest

from pvl.analysis.comparison import (
    PhysicsComparisonRequest,
    PhysicsSample,
    compare_physics_series,
)


MESH = "a" * 64


def _sample(state: str, x: float, repetition: int, value: float, *, temp: float = 293.15, mesh: str = MESH):
    return PhysicsSample(
        run_id=f"{state}-{x}-{repetition}",
        state_id=state,
        repetition_index=repetition,
        parameter_value=x,
        metrics={"signal": value, "temperature_k": temp},
        mesh_configuration_hash=mesh,
        configuration_hash=(f"{repetition + 1:x}" * 64)[:64],
    )


def _replicated_series(values: list[float], *, state: str = "test") -> tuple[PhysicsSample, ...]:
    samples: list[PhysicsSample] = []
    for index, value in enumerate(values):
        for repetition, offset in enumerate((-0.0002, 0.0, 0.0002)):
            samples.append(_sample(state, float(index), repetition, value + offset))
    return tuple(samples)


def test_linear_repeatable_series_has_no_transition_candidate():
    request = PhysicsComparisonRequest(
        comparison_id="linear",
        parameter_name="coil_current_a",
        metric_name="signal",
        samples=_replicated_series([0.0, 1.0, 2.0, 3.0, 4.0, 5.0]),
    )
    result = compare_physics_series(request)
    assert result.repeatability_gate_passed
    assert result.mesh_identity_gate_passed
    assert result.transition_candidate_count == 0
    assert result.unexplained_residual_claim_allowed is False
    assert result.portal_interpretation_allowed is False
    assert "no abrupt transition" in result.next_action


def test_abrupt_repeatable_derivative_is_only_physics_investigation_candidate():
    # Slightly varying baseline slopes keep MAD finite; one deliberately sharp change is then a
    # large robust derivative outlier without weakening the default transition threshold.
    values = [0.0, 1.0, 2.01, 3.00, 4.02, 24.0, 25.01, 25.99, 27.0, 28.02]
    result = compare_physics_series(
        PhysicsComparisonRequest(
            comparison_id="step",
            parameter_name="coil_current_a",
            metric_name="signal",
            samples=_replicated_series(values),
        )
    )
    assert result.repeatability_gate_passed
    assert result.transition_candidate_count >= 1
    assert any(item.transition_candidate for item in result.adjacent_differences)
    assert result.portal_interpretation_allowed is False
    assert "investigate transition" in result.next_action


def test_nonrepeatable_state_blocks_transition_interpretation():
    samples = list(_replicated_series([0.0, 1.0, 2.0, 20.0, 21.0, 22.0]))
    # Replace the three repetitions at x=3 with a deliberately unstable state.
    samples = [sample for sample in samples if sample.parameter_value != 3.0]
    samples.extend(
        [
            _sample("test", 3.0, 0, 5.0),
            _sample("test", 3.0, 1, 20.0),
            _sample("test", 3.0, 2, 40.0),
        ]
    )
    result = compare_physics_series(
        PhysicsComparisonRequest(
            comparison_id="nonrepeatable",
            parameter_name="coil_current_a",
            metric_name="signal",
            samples=tuple(samples),
        )
    )
    assert not result.repeatability_gate_passed
    assert result.portal_interpretation_allowed is False
    assert "repeat" in result.next_action


def test_mesh_identity_mismatch_blocks_physics_transition_gate():
    samples = list(_replicated_series([0.0, 1.0, 2.0, 3.0]))
    target = next(index for index, sample in enumerate(samples) if sample.parameter_value == 2.0 and sample.repetition_index == 2)
    original = samples[target]
    samples[target] = original.model_copy(update={"mesh_configuration_hash": "b" * 64})
    result = compare_physics_series(
        PhysicsComparisonRequest(
            comparison_id="mesh-mismatch",
            parameter_name="coil_current_a",
            metric_name="signal",
            samples=tuple(samples),
        )
    )
    assert not result.mesh_identity_gate_passed
    assert "mesh-identity" in result.next_action
    assert result.portal_interpretation_allowed is False


def test_strong_temperature_tracking_is_flagged_as_ordinary_explanation():
    samples: list[PhysicsSample] = []
    for index in range(8):
        for repetition in range(3):
            temperature = 293.15 + index * 0.5 + repetition * 0.001
            signal = 10.0 * temperature + repetition * 0.0001
            samples.append(_sample("thermal-series", float(index), repetition, signal, temp=temperature))
    result = compare_physics_series(
        PhysicsComparisonRequest(
            comparison_id="thermal",
            parameter_name="input_power_w",
            metric_name="signal",
            temperature_metric_name="temperature_k",
            samples=tuple(samples),
        )
    )
    assert result.thermal_correlation is not None
    assert result.thermal_correlation > 0.99
    assert result.thermal_tracking_flag
    assert "thermally correlated" in result.next_action
    assert result.portal_interpretation_allowed is False


def test_control_subtraction_is_explicit_and_does_not_authorize_hypothesis_layer():
    samples = []
    for repetition in range(3):
        samples.append(_sample("control", 0.0, repetition, 2.0 + repetition * 0.001))
        samples.append(_sample("active", 1.0, repetition, 5.0 + repetition * 0.001))
    result = compare_physics_series(
        PhysicsComparisonRequest(
            comparison_id="control-subtraction",
            parameter_name="condition",
            metric_name="signal",
            control_state_id="control",
            samples=tuple(samples),
        )
    )
    active = next(item for item in result.state_summaries if item.state_id == "active")
    assert active.control_subtracted_mean == pytest.approx(3.0)
    assert result.control_mean == pytest.approx(2.001)
    assert result.portal_interpretation_allowed is False


def test_unverified_sample_cannot_enter_physics_comparison():
    with pytest.raises(ValueError, match="unverified"):
        PhysicsSample(
            run_id="bad",
            state_id="bad",
            repetition_index=0,
            parameter_value=0.0,
            metrics={"signal": 1.0},
            mesh_configuration_hash=MESH,
            configuration_hash="c" * 64,
            checksum_verified=False,
        )
