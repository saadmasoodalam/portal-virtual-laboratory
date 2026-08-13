from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from pvl.core.models import POC001Config
from pvl.core.physics import circular_coil_on_axis_b_t, relative_error


@dataclass(frozen=True)
class AnalyticalResult:
    z_m: np.ndarray
    b_t: np.ndarray


def analytical_reference(config: POC001Config) -> AnalyticalResult:
    z = np.asarray(config.probe_z_m, dtype=float)
    b = circular_coil_on_axis_b_t(
        z,
        radius_m=config.coil.radius_m,
        turns=config.coil.turns,
        current_a=config.coil.signed_current_a,
        center_z_m=config.coil.center_z_m,
    )
    return AnalyticalResult(z_m=z, b_t=np.asarray(b, dtype=float))


def compare_fem_to_analytic(reference: AnalyticalResult, fem_b_t: np.ndarray) -> dict[str, float]:
    errors = relative_error(reference.b_t, fem_b_t)
    return {
        "max_relative_error": float(np.max(errors)),
        "mean_relative_error": float(np.mean(errors)),
        "rms_relative_error": float(np.sqrt(np.mean(errors**2))),
    }
