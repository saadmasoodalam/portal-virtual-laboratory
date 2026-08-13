from __future__ import annotations

import random

from pydantic import Field

from pvl.core.models import FrozenModel
from pvl.experiments.models import CoilDriveState, DriveMode


class PlannedDCState(FrozenModel):
    state_id: str
    coil_a: CoilDriveState
    coil_b: CoilDriveState


class MatrixRun(FrozenModel):
    sequence_index: int = Field(ge=0)
    repetition_index: int = Field(ge=1)
    state_id: str
    coil_a: CoilDriveState
    coil_b: CoilDriveState


def _off() -> CoilDriveState:
    return CoilDriveState(mode=DriveMode.OFF)


def _dc(current_a: float, polarity: int) -> CoilDriveState:
    return CoilDriveState(mode=DriveMode.DC, current_a=current_a, polarity=polarity)


def build_rig_v1_dc_baseline_states(current_a: float = 1.0) -> tuple[PlannedDCState, ...]:
    """Return the controlled low-energy DC state family.

    Current polarity is kept separate from signed-frequency convention. The explicit positive and
    negative variants allow reversal effects to be compared without hiding them inside labels.
    """
    if current_a <= 0.0:
        raise ValueError("current_a must be positive")
    return (
        PlannedDCState(state_id="off_off", coil_a=_off(), coil_b=_off()),
        PlannedDCState(state_id="a_positive", coil_a=_dc(current_a, 1), coil_b=_off()),
        PlannedDCState(state_id="a_negative", coil_a=_dc(current_a, -1), coil_b=_off()),
        PlannedDCState(state_id="b_positive", coil_a=_off(), coil_b=_dc(current_a, 1)),
        PlannedDCState(state_id="b_negative", coil_a=_off(), coil_b=_dc(current_a, -1)),
        PlannedDCState(
            state_id="both_same_positive",
            coil_a=_dc(current_a, 1),
            coil_b=_dc(current_a, 1),
        ),
        PlannedDCState(
            state_id="both_same_negative",
            coil_a=_dc(current_a, -1),
            coil_b=_dc(current_a, -1),
        ),
        PlannedDCState(
            state_id="both_opposed_ab",
            coil_a=_dc(current_a, 1),
            coil_b=_dc(current_a, -1),
        ),
        PlannedDCState(
            state_id="both_opposed_ba",
            coil_a=_dc(current_a, -1),
            coil_b=_dc(current_a, 1),
        ),
    )


def randomized_repeated_dc_matrix(
    *,
    current_a: float = 1.0,
    repetitions: int = 3,
    seed: int = 0,
) -> tuple[MatrixRun, ...]:
    """Build deterministic randomized blocks with OFF/OFF first in each repetition.

    Rig v1 calls for randomized order after a baseline and repeated runs. Each block therefore
    starts with the OFF/OFF control, then shuffles all active states with one seeded RNG stream.
    """
    if repetitions < 1:
        raise ValueError("repetitions must be at least one")
    if seed < 0:
        raise ValueError("seed must be non-negative")

    states = build_rig_v1_dc_baseline_states(current_a)
    baseline = states[0]
    active = list(states[1:])
    rng = random.Random(seed)
    runs: list[MatrixRun] = []
    sequence = 0

    for repetition in range(1, repetitions + 1):
        runs.append(
            MatrixRun(
                sequence_index=sequence,
                repetition_index=repetition,
                state_id=baseline.state_id,
                coil_a=baseline.coil_a,
                coil_b=baseline.coil_b,
            )
        )
        sequence += 1
        shuffled = active.copy()
        rng.shuffle(shuffled)
        for state in shuffled:
            runs.append(
                MatrixRun(
                    sequence_index=sequence,
                    repetition_index=repetition,
                    state_id=state.state_id,
                    coil_a=state.coil_a,
                    coil_b=state.coil_b,
                )
            )
            sequence += 1
    return tuple(runs)
