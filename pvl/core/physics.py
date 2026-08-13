from __future__ import annotations

import math
import numpy as np

MU0 = 4.0e-7 * math.pi


def circular_coil_on_axis_b_t(
    z_m: float | np.ndarray,
    *,
    radius_m: float,
    turns: int,
    current_a: float,
    center_z_m: float = 0.0,
) -> float | np.ndarray:
    """Analytical Bz for an ideal thin circular N-turn coil in vacuum/air."""
    z = np.asarray(z_m, dtype=float) - center_z_m
    numerator = MU0 * turns * current_a * radius_m**2
    denominator = 2.0 * (radius_m**2 + z**2) ** 1.5
    result = numerator / denominator
    if np.ndim(z_m) == 0:
        return float(result)
    return result


def relative_error(reference: np.ndarray, candidate: np.ndarray) -> np.ndarray:
    reference = np.asarray(reference, dtype=float)
    candidate = np.asarray(candidate, dtype=float)
    if np.any(reference == 0):
        raise ValueError("relative error is undefined for zero reference values")
    return np.abs(candidate - reference) / np.abs(reference)
