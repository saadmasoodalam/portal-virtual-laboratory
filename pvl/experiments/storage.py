from __future__ import annotations

import json
from pathlib import Path

from pydantic import ConfigDict

from pvl.core.models import FrozenModel
from pvl.experiments.models import RunManifest


class RunStorageLayout(FrozenModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    root: str
    experiment_json: str
    geometry_json: str
    materials_json: str
    solver_json: str
    mesh_msh: str
    solver_input_pro: str
    solver_stdout_log: str
    solver_stderr_log: str
    raw_dir: str
    fields_vtu: str
    metrics_json: str
    summary_csv: str
    environment_json: str
    manifest_json: str


def run_storage_layout(results_root: Path, experiment_id: str, run_id: str) -> RunStorageLayout:
    root = results_root / experiment_id / run_id
    return RunStorageLayout(
        root=str(root),
        experiment_json=str(root / "experiment.json"),
        geometry_json=str(root / "geometry.json"),
        materials_json=str(root / "materials.json"),
        solver_json=str(root / "solver.json"),
        mesh_msh=str(root / "mesh.msh"),
        solver_input_pro=str(root / "solver_input.pro"),
        solver_stdout_log=str(root / "solver_stdout.log"),
        solver_stderr_log=str(root / "solver_stderr.log"),
        raw_dir=str(root / "raw"),
        fields_vtu=str(root / "fields.vtu"),
        metrics_json=str(root / "metrics.json"),
        summary_csv=str(root / "summary.csv"),
        environment_json=str(root / "environment.json"),
        manifest_json=str(root / "manifest.json"),
    )


def initialize_run_storage(layout: RunStorageLayout, manifest: RunManifest) -> Path:
    root = Path(layout.root)
    root.mkdir(parents=True, exist_ok=False)
    Path(layout.raw_dir).mkdir()
    Path(layout.manifest_json).write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return root
