from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from pvl.core.models import HarmonicDriveConfig, POC003Config
from pvl.validation.poc002 import finite_winding_component


@dataclass(frozen=True)
class HarmonicFieldResult:
    z_m: np.ndarray
    b_phasor_t: np.ndarray

    @property
    def peak_amplitude_t(self) -> np.ndarray:
        return np.abs(self.b_phasor_t)

    @property
    def rms_amplitude_t(self) -> np.ndarray:
        return np.abs(self.b_phasor_t) / math.sqrt(2.0)


@dataclass(frozen=True)
class POC003GateResult:
    passed: bool
    criteria: dict[str, bool]
    observed: dict[str, float]
    tolerances: dict[str, float]

    def as_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "criteria": self.criteria,
            "observed": self.observed,
            "tolerances": self.tolerances,
        }


def _coil_spatial_amplitudes(config: POC003Config) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    z = np.asarray(config.probe_z_m, dtype=float)
    a = finite_winding_component(z, config.coil_a, config.source_section)
    b = finite_winding_component(z, config.coil_b, config.source_section)
    return z, a, b


def dual_coil_phasor_reference(config: POC003Config) -> HarmonicFieldResult:
    """Canonical +frequency phasor for the two real sinusoidal coil drives.

    A real current ``A cos(s*omega*t + phi)`` is represented at positive frequency by the
    phasor ``A exp(i*s*phi)``. Thus changing only the sign of omega at zero phase leaves the
    physical scalar sinusoid unchanged; for non-zero phase it conjugates the phase convention.
    """
    z, field_a, field_b = _coil_spatial_amplitudes(config)
    phase_a = config.drive_a.canonical_positive_frequency_phase_rad
    phase_b = config.drive_b.canonical_positive_frequency_phase_rad
    phasor = field_a * np.exp(1j * phase_a) + field_b * np.exp(1j * phase_b)
    return HarmonicFieldResult(z_m=z, b_phasor_t=np.asarray(phasor, dtype=complex))


def sample_phasor_waveform(config: POC003Config, time_s: np.ndarray) -> np.ndarray:
    """Return B(z,t) from the canonical positive-frequency phasor representation."""
    time = np.asarray(time_s, dtype=float)
    result = dual_coil_phasor_reference(config)
    omega = 2.0 * math.pi * config.drive_a.frequency_hz
    carrier = np.exp(1j * omega * time[:, None])
    return np.real(carrier * result.b_phasor_t[None, :])


def sample_direct_signed_omega_waveform(config: POC003Config, time_s: np.ndarray) -> np.ndarray:
    """Return B(z,t) by directly evaluating each signed-frequency real cosine drive."""
    time = np.asarray(time_s, dtype=float)
    _, field_a, field_b = _coil_spatial_amplitudes(config)
    angle_a = (
        config.drive_a.signed_angular_frequency_rad_s * time[:, None] + config.drive_a.phase_rad
    )
    angle_b = (
        config.drive_b.signed_angular_frequency_rad_s * time[:, None] + config.drive_b.phase_rad
    )
    return field_a[None, :] * np.cos(angle_a) + field_b[None, :] * np.cos(angle_b)


def one_cycle_times(config: POC003Config) -> np.ndarray:
    period = 1.0 / config.drive_a.frequency_hz
    return np.linspace(0.0, period, config.samples_per_cycle, endpoint=False)


def compare_phasor_and_direct_time_domain(config: POC003Config) -> dict[str, float]:
    times = one_cycle_times(config)
    phasor_waveform = sample_phasor_waveform(config, times)
    direct_waveform = sample_direct_signed_omega_waveform(config, times)
    difference = np.abs(phasor_waveform - direct_waveform)
    scale = max(float(np.max(np.abs(direct_waveform))), np.finfo(float).tiny)
    return {
        "max_absolute_difference_t": float(np.max(difference)),
        "max_peak_normalized_difference": float(np.max(difference) / scale),
        "rms_peak_normalized_difference": float(np.sqrt(np.mean(difference**2)) / scale),
    }


def _normalized_complex_difference(candidate: np.ndarray, reference: np.ndarray) -> float:
    scale = max(float(np.max(np.abs(reference))), np.finfo(float).tiny)
    return float(np.max(np.abs(candidate - reference)) / scale)


def _center_index(config: POC003Config) -> int:
    z = np.asarray(config.probe_z_m, dtype=float)
    matches = np.where(np.isclose(z, 0.0, rtol=0.0, atol=1e-14))[0]
    if not matches.size:
        raise ValueError("POC-003 gate requires a z=0 probe")
    return int(matches[0])


def evaluate_poc003_gate(
    *,
    algebraic_tolerance: float = 1e-10,
    cancellation_tolerance: float = 1e-10,
    time_domain_tolerance: float = 1e-12,
) -> POC003GateResult:
    """Validate phase and signed-frequency conventions before dynamic material coupling.

    This gate deliberately tests identities that must hold in a linear, lossless, coaxial
    scalar-field baseline. It prevents PVL from assigning anomalous meaning to phase or to the
    sign of omega before a geometry/material model exists in which those controls can produce a
    genuinely distinct physical response.
    """
    base = POC003Config()
    center = _center_index(base)
    _, spatial_a, spatial_b = _coil_spatial_amplitudes(base)
    single_center = float((spatial_a[center] + spatial_b[center]) / 2.0)
    field_scale = max(abs(single_center), np.finfo(float).tiny)

    same = dual_coil_phasor_reference(base).b_phasor_t
    expected_same_center = 2.0 * single_center
    same_center_error = abs(same[center] - expected_same_center) / abs(expected_same_center)

    phase_opposed = base.model_copy(
        update={
            "drive_b": base.drive_b.model_copy(update={"phase_rad": math.pi}),
        }
    )
    opposed = dual_coil_phasor_reference(phase_opposed).b_phasor_t
    opposed_center_residual = abs(opposed[center]) / field_scale

    quadrature = base.model_copy(
        update={
            "drive_b": base.drive_b.model_copy(update={"phase_rad": math.pi / 2.0}),
        }
    )
    quadrature_field = dual_coil_phasor_reference(quadrature).b_phasor_t
    expected_quadrature_center = math.sqrt(2.0) * single_center
    quadrature_center_magnitude_error = (
        abs(abs(quadrature_field[center]) - expected_quadrature_center)
        / expected_quadrature_center
    )

    omega_reversed_zero_phase = base.model_copy(
        update={
            "drive_b": base.drive_b.model_copy(update={"omega_sign": -1}),
        }
    )
    omega_zero_field = dual_coil_phasor_reference(omega_reversed_zero_phase).b_phasor_t
    omega_zero_phase_difference = _normalized_complex_difference(omega_zero_field, same)

    phase_value = 0.73
    plus_phase = base.model_copy(
        update={
            "drive_b": HarmonicDriveConfig(
                frequency_hz=base.drive_b.frequency_hz,
                phase_rad=phase_value,
                omega_sign=1,
            )
        }
    )
    minus_equivalent = base.model_copy(
        update={
            "drive_b": HarmonicDriveConfig(
                frequency_hz=base.drive_b.frequency_hz,
                phase_rad=-phase_value,
                omega_sign=-1,
            )
        }
    )
    plus_phase_field = dual_coil_phasor_reference(plus_phase).b_phasor_t
    minus_equivalent_field = dual_coil_phasor_reference(minus_equivalent).b_phasor_t
    signed_frequency_phase_equivalence = _normalized_complex_difference(
        minus_equivalent_field, plus_phase_field
    )

    conjugate_plus = base.model_copy(
        update={
            "drive_a": HarmonicDriveConfig(
                frequency_hz=base.drive_a.frequency_hz,
                phase_rad=0.31,
                omega_sign=1,
            ),
            "drive_b": HarmonicDriveConfig(
                frequency_hz=base.drive_b.frequency_hz,
                phase_rad=-0.67,
                omega_sign=1,
            ),
        }
    )
    conjugate_minus = conjugate_plus.model_copy(
        update={
            "drive_a": conjugate_plus.drive_a.model_copy(update={"omega_sign": -1}),
            "drive_b": conjugate_plus.drive_b.model_copy(update={"omega_sign": -1}),
        }
    )
    plus_field = dual_coil_phasor_reference(conjugate_plus).b_phasor_t
    minus_field = dual_coil_phasor_reference(conjugate_minus).b_phasor_t
    global_omega_reversal_conjugacy = _normalized_complex_difference(
        minus_field, np.conjugate(plus_field)
    )
    global_omega_reversal_magnitude_difference = float(
        np.max(np.abs(np.abs(minus_field) - np.abs(plus_field)))
        / max(float(np.max(np.abs(plus_field))), np.finfo(float).tiny)
    )

    mixed = base.model_copy(
        update={
            "drive_a": HarmonicDriveConfig(
                frequency_hz=base.drive_a.frequency_hz,
                phase_rad=0.37,
                omega_sign=1,
            ),
            "drive_b": HarmonicDriveConfig(
                frequency_hz=base.drive_b.frequency_hz,
                phase_rad=0.61,
                omega_sign=-1,
            ),
        }
    )
    time_comparison = compare_phasor_and_direct_time_domain(mixed)
    time_domain_difference = time_comparison["max_peak_normalized_difference"]

    observed = {
        "same_phase_center_relative_error": float(same_center_error),
        "phase_pi_center_cancellation_normalized": float(opposed_center_residual),
        "quadrature_center_magnitude_relative_error": float(quadrature_center_magnitude_error),
        "zero_phase_single_omega_reversal_difference": float(omega_zero_phase_difference),
        "signed_frequency_phase_equivalence_difference": float(signed_frequency_phase_equivalence),
        "global_omega_reversal_conjugacy_difference": float(global_omega_reversal_conjugacy),
        "global_omega_reversal_magnitude_difference": float(
            global_omega_reversal_magnitude_difference
        ),
        "phasor_vs_direct_time_domain_difference": float(time_domain_difference),
    }
    criteria = {
        "same_phase_addition": same_center_error <= algebraic_tolerance,
        "phase_pi_center_cancellation": opposed_center_residual <= cancellation_tolerance,
        "quadrature_resultant": quadrature_center_magnitude_error <= algebraic_tolerance,
        "zero_phase_omega_sign_equivalence": omega_zero_phase_difference <= algebraic_tolerance,
        "signed_frequency_phase_equivalence": (
            signed_frequency_phase_equivalence <= algebraic_tolerance
        ),
        "global_omega_reversal_is_conjugate": (
            global_omega_reversal_conjugacy <= algebraic_tolerance
        ),
        "global_omega_reversal_preserves_magnitude": (
            global_omega_reversal_magnitude_difference <= algebraic_tolerance
        ),
        "phasor_matches_direct_signed_omega_time_domain": (
            time_domain_difference <= time_domain_tolerance
        ),
    }
    tolerances = {
        "algebraic_tolerance": algebraic_tolerance,
        "cancellation_tolerance": cancellation_tolerance,
        "time_domain_tolerance": time_domain_tolerance,
    }
    return POC003GateResult(
        passed=all(criteria.values()),
        criteria=criteria,
        observed=observed,
        tolerances=tolerances,
    )
