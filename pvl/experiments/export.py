from __future__ import annotations

import json
from pathlib import Path

from pvl.experiments.models import ExperimentConfig
from pvl.experiments.planning import PlannedRun


def write_experiment_plan(
    config: ExperimentConfig,
    runs: tuple[PlannedRun, ...],
    output_dir: Path,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    experiment_path = output_dir / "experiment.json"
    matrix_path = output_dir / "run_matrix.json"
    experiment_payload = {
        "configuration": config.model_dump(mode="json"),
        "configuration_hash": config.configuration_hash(),
        "physics_state_hash": config.physics_state_hash(),
    }
    matrix_payload = [
        {
            "run_id": run.run_id,
            "sequence_index": run.sequence_index,
            "repetition_index": run.repetition_index,
            "state_id": run.state_id,
            "configuration_hash": run.configuration.configuration_hash(),
            "physics_state_hash": run.configuration.physics_state_hash(),
            "coil_a": run.configuration.coil_a.model_dump(mode="json"),
            "coil_b": run.configuration.coil_b.model_dump(mode="json"),
        }
        for run in runs
    ]
    experiment_path.write_text(json.dumps(experiment_payload, indent=2), encoding="utf-8")
    matrix_path.write_text(json.dumps(matrix_payload, indent=2), encoding="utf-8")
    return experiment_path, matrix_path
