from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from pvl.core.models import POC003Config
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
