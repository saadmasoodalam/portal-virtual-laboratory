from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from pvl.core.poc004_models import POC004Config
from pvl.core.physics import MU0


@dataclass(frozen=True)
class SlabAnalyticalResult:
    x_m: np.ndarray
    vector_potential_t_m: np.ndarray
    magnetic_flux_density_t: np.ndarray
    induced_current_density_a_m2: np.ndarray


def skin_depth_m(config: POC004Config) -> float:
    mu = MU0 * config.relative_permeability
    omega = 2.0 * math.pi * config.frequency_hz
    return math.sqrt(2.0 / (omega * mu * config.conductivity_s_m))


def propagation_constant_per_m(config: POC004Config) -> complex:
    """Return k = sqrt(i omega mu sigma) = (1+i)/delta for exp(+i omega t)."""
    delta = skin_depth_m(config)
    return complex(1.0, 1.0) / delta


def analytical_slab_reference(
    config: POC004Config,
    x_m: np.ndarray | None = None,
) -> SlabAnalyticalResult:
    """Exact finite-slab solution for A_z(0)=A0 and A_z(L)=0.

    In a uniform conductor with the exp(+i omega t) convention,

        curl(nu curl A) + i omega sigma A = 0

    reduces to A'' = k^2 A with k^2 = i omega mu sigma. The finite-slab solution is

        A(x) = A0 sinh(k(L-x)) / sinh(kL).

    B_y = -dA/dx and J_z = -i omega sigma A.
    """
    x = np.asarray(config.probe_x_m if x_m is None else x_m, dtype=float)
    if np.any(x < 0.0) or np.any(x > config.length_m):
        raise ValueError("analytical slab sample points must lie inside the slab")

    k = propagation_constant_per_m(config)
    length = config.length_m
    a0 = config.boundary_vector_potential_t_m
    denominator = np.sinh(k * length)
    a = a0 * np.sinh(k * (length - x)) / denominator
    b_y = a0 * k * np.cosh(k * (length - x)) / denominator
    omega = 2.0 * math.pi * config.frequency_hz
    j_z = -1j * omega * config.conductivity_s_m * a

    return SlabAnalyticalResult(
        x_m=x,
        vector_potential_t_m=np.asarray(a, dtype=complex),
        magnetic_flux_density_t=np.asarray(b_y, dtype=complex),
        induced_current_density_a_m2=np.asarray(j_z, dtype=complex),
    )


def average_joule_power_density_w_m3(config: POC004Config, a_t_m: np.ndarray) -> np.ndarray:
    """Time-averaged Joule power density for peak-valued harmonic phasors."""
    omega = 2.0 * math.pi * config.frequency_hz
    return 0.5 * config.conductivity_s_m * omega**2 * np.abs(a_t_m) ** 2


def complex_peak_normalized_error(reference: np.ndarray, candidate: np.ndarray) -> dict[str, float]:
    ref = np.asarray(reference, dtype=complex)
    cand = np.asarray(candidate, dtype=complex)
    if ref.shape != cand.shape:
        raise ValueError("reference and candidate must have matching shapes")
    scale = max(float(np.max(np.abs(ref))), np.finfo(float).tiny)
    normalized = np.abs(cand - ref) / scale
    return {
        "reference_peak_abs": scale,
        "max_peak_normalized_complex_error": float(np.max(normalized)),
        "mean_peak_normalized_complex_error": float(np.mean(normalized)),
        "rms_peak_normalized_complex_error": float(np.sqrt(np.mean(normalized**2))),
    }
