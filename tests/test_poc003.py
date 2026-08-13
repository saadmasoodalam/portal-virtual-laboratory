import math

import numpy as np
import pytest
from pydantic import ValidationError

from pvl.core.models import HarmonicDriveConfig, POC003Config
from pvl.validation.poc003 import (
    compare_phasor_and_direct_time_domain,
    dual_coil_phasor_reference,
    evaluate_poc003_gate,
)


def test_negative_frequency_maps_to_conjugate_phase_convention():
    plus = HarmonicDriveConfig(frequency_hz=100.0, phase_rad=0.7, omega_sign=1)
    minus = HarmonicDriveConfig(frequency_hz=100.0, phase_rad=0.7, omega_sign=-1)
    assert plus.canonical_positive_frequency_phase_rad == pytest.approx(0.7)
    assert minus.canonical_positive_frequency_phase_rad == pytest.approx(-0.7)
    assert plus.signed_angular_frequency_rad_s == pytest.approx(2 * math.pi * 100.0)
    assert minus.signed_angular_frequency_rad_s == pytest.approx(-2 * math.pi * 100.0)


def test_poc003_requires_common_frequency_magnitude():
    with pytest.raises(ValidationError):
        POC003Config(drive_b={"frequency_hz": 101.0, "phase_rad": 0.0, "omega_sign": 1})


def test_zero_phase_omega_sign_change_is_same_scalar_phasor():
    base = POC003Config()
    reversed_b = base.model_copy(
        update={"drive_b": base.drive_b.model_copy(update={"omega_sign": -1})}
    )
    a = dual_coil_phasor_reference(base).b_phasor_t
    b = dual_coil_phasor_reference(reversed_b).b_phasor_t
    assert np.allclose(a, b, rtol=0.0, atol=0.0)


def test_pi_phase_cancels_symmetric_pair_at_midplane():
    base = POC003Config()
    opposed = base.model_copy(
        update={"drive_b": base.drive_b.model_copy(update={"phase_rad": math.pi})}
    )
    result = dual_coil_phasor_reference(opposed)
    center = len(result.z_m) // 2
    scale = np.max(np.abs(result.b_phasor_t))
    assert abs(result.b_phasor_t[center]) / scale < 1e-12


def test_phasor_matches_direct_signed_frequency_time_waveform():
    base = POC003Config()
    mixed = base.model_copy(
        update={
            "drive_a": HarmonicDriveConfig(frequency_hz=100.0, phase_rad=0.37, omega_sign=1),
            "drive_b": HarmonicDriveConfig(frequency_hz=100.0, phase_rad=0.61, omega_sign=-1),
        }
    )
    metrics = compare_phasor_and_direct_time_domain(mixed)
    assert metrics["max_peak_normalized_difference"] < 1e-12


def test_poc003_invariance_gate_passes():
    gate = evaluate_poc003_gate()
    assert gate.passed
    assert all(gate.criteria.values())
