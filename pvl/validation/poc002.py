from __future__ import annotations

import numpy as np

from pvl.core.models import CoilConfig, CoilSourceSectionConfig, POC002Config
from pvl.core.physics import MU0, circular_coil_on_axis_b_t
from pvl.validation.poc001 import AnalyticalResult


def dual_filament_reference(config: POC002Config) -> AnalyticalResult:
    """Analytical superposition of two ideal coaxial circular coils."""
    z = np.asarray(config.probe_z_m, dtype=float)
    field = np.zeros_like(z)
    for coil in (config.coil_a, config.coil_b):
        field += np.asarray(
            circular_coil_on_axis_b_t(
                z,
                radius_m=coil.radius_m,
                turns=coil.turns,
                current_a=coil.signed_current_a,
                center_z_m=coil.center_z_m,
            ),
            dtype=float,
        )
    return AnalyticalResult(z_m=z, b_t=field)


def finite_winding_component(
    z_m: np.ndarray,
    coil: CoilConfig,
    source_section: CoilSourceSectionConfig,
    *,
    quadrature_order: int = 24,
) -> np.ndarray:
    """Integrate one homogenized rectangular winding section over exact loop kernels."""
    if quadrature_order < 2:
        raise ValueError("quadrature_order must be at least 2")

    z = np.asarray(z_m, dtype=float)
    nodes, weights = np.polynomial.legendre.leggauss(quadrature_order)
    radial_half = source_section.radial_thickness_m / 2.0
    axial_half = source_section.axial_height_m / 2.0
    radii = coil.radius_m + radial_half * nodes
    source_z = coil.center_z_m + axial_half * nodes
    wr = radial_half * weights
    wz = axial_half * weights
    ampere_turn_density = coil.turns * coil.signed_current_a / source_section.area_m2

    out = np.zeros_like(z, dtype=float)
    for ri, wri in zip(radii, wr):
        dz = z[:, None] - source_z[None, :]
        kernel = MU0 * ri**2 / (2.0 * (ri**2 + dz**2) ** 1.5)
        out += ampere_turn_density * wri * np.sum(kernel * wz[None, :], axis=1)
    return out


def dual_finite_source_reference(
    config: POC002Config,
    *,
    quadrature_order: int = 24,
) -> AnalyticalResult:
    """Reference matching the two finite rectangular winding sections used by FEM."""
    z = np.asarray(config.probe_z_m, dtype=float)
    field = finite_winding_component(
        z, config.coil_a, config.source_section, quadrature_order=quadrature_order
    )
    field += finite_winding_component(
        z, config.coil_b, config.source_section, quadrature_order=quadrature_order
    )
    return AnalyticalResult(z_m=z, b_t=field)


def compare_dual_fem(reference: AnalyticalResult, candidate_b_t: np.ndarray) -> dict[str, float]:
    """Compare dual-coil fields with a zero-safe global field normalization.

    Opposed identical coils have a physically required zero at the mid-plane, so pointwise
    relative error is undefined there. Errors are therefore normalized to the peak magnitude
    of the analytical field across the probe set.
    """
    ref = np.asarray(reference.b_t, dtype=float)
    candidate = np.asarray(candidate_b_t, dtype=float)
    if ref.shape != candidate.shape:
        raise ValueError("reference and candidate must have matching shapes")
    scale = float(np.max(np.abs(ref)))
    if scale <= np.finfo(float).tiny:
        raise ValueError("dual-coil reference has no non-zero field scale")
    normalized = np.abs(candidate - ref) / scale
    return {
        "reference_peak_abs_t": scale,
        "max_peak_normalized_absolute_error": float(np.max(normalized)),
        "mean_peak_normalized_absolute_error": float(np.mean(normalized)),
        "rms_peak_normalized_absolute_error": float(np.sqrt(np.mean(normalized**2))),
    }
