from pathlib import Path

from pydantic import Field

from pvl.core.models import FrozenModel
from pvl.experiments.matrix import randomized_repeated_dc_matrix
from pvl.experiments.models import ExperimentConfig
from pvl.experiments.storage import run_storage_layout


class PlannedRun(FrozenModel):
    run_id: str
    sequence_index: int = Field(ge=0)
    repetition_index: int = Field(ge=1)
    state_id: str
    configuration: ExperimentConfig


def plan_rig_v1_dc_experiment(base: ExperimentConfig, current_a: float) -> tuple[PlannedRun, ...]:
    rows = randomized_repeated_dc_matrix(
        current_a=current_a,
        repetitions=base.repetitions,
        seed=base.randomization_seed,
    )
    result = []
    for row in rows:
        config = base.model_copy(update={"coil_a": row.coil_a, "coil_b": row.coil_b})
        result.append(PlannedRun(
            run_id=f"{base.experiment_id}-r{row.repetition_index:02d}-s{row.sequence_index:04d}",
            sequence_index=row.sequence_index,
            repetition_index=row.repetition_index,
            state_id=row.state_id,
            configuration=config,
        ))
    return tuple(result)


def planned_run_layout(run: PlannedRun, results_root: Path):
    return run_storage_layout(results_root, run.configuration.experiment_id, run.run_id)
