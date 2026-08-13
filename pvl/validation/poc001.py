from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from pvl.core.models import POC001Config
from pvl.core.physics import MU0, circular_coil_on_axis_b_t, relative_error


@dataclass(frozen=True)
class AnalyticalResult:
    z_m: np.ndarray
    b_t: np.ndarray


def analytical_reference(config: POC001Config) -> AnalyticalResult:
    """Ideal filamentary circular-coil reference used as the textbook oracle."""
    z = np.asarray(config.probe_z_m, dtype=float)
    b = circular_coil_on_axis_b_t(
        z,
        radius_m=config.coil.radius_m,
        turns=config.coil.turns,
        current_a=config.coil.signed_current_a,
        center_z_m=config.coil.center_z_m,
    )
    return AnalyticalResult(z_m=z, b_t=np.asarray(b, dtype=float))


def finite_source_reference(config: POC001Config, *, quadrature_order: int = 24) -> AnalyticalResult:
    """Axis field of PVL's finite rectangular winding section.

    The FEM source is a homogenized 2 mm x 2 mm winding cross-section rather than an
    infinitesimally thin filament.  This oracle integrates the exact circular-loop
    on-axis field over that rectangular cross-section with uniform ampere-turn
    density, isolating numerical FEM error from the tiny physical difference between
    the finite source and the textbook filament model.
    """
    if quadrature_order < 2:
        raise ValueError("quadrature_order must be at least 2")

    z = np.asarray(config.probe_z_m, dtype=float)
    c = config.coil
    s = config.source_section
    nodes, weights = np.polynomial.legendre.leggauss(quadrature_order)

    radial_half = s.radial_thickness_m / 2.0
    axial_half = s.axial_height_m / 2.0
    radii = c.radius_m + radial_half * nodes
    source_z = c.center_z_m + axial_half * nodes
    wr = radial_half * weights
    wz = axial_half * weights
    ampere_turn_density = c.turns * c.signed_current_a / s.area_m2

    out = np.zeros_like(z, dtype=float)
    for ri, wri in zip(radii, wr):
        dz = z[:, None] - source_z[None, :]
        kernel = MU0 * ri**2 / (2.0 * (ri**2 + dz**2) ** 1.5)
        out += ampere_turn_density * wri * np.sum(kernel * wz[None, :], axis=1)

    return AnalyticalResult(z_m=z, b_t=out)


def compare_fem_to_analytic(reference: AnalyticalResult, fem_b_t: np.ndarray) -> dict[str, float]:
    errors = relative_error(reference.b_t, fem_b_t)
    return {
        "max_relative_error": float(np.max(errors)),
        "mean_relative_error": float(np.mean(errors)),
        "rms_relative_error": float(np.sqrt(np.mean(errors**2))),
    }
