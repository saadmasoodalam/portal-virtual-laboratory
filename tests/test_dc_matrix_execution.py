from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from pvl.experiments.models import ExperimentConfig
from pvl.experiments.package import persist_dc_experiment_package
from pvl.geometry.exploratory import architecture_example_rig_v1
from pvl.materials.library import load_builtin_material_library
from pvl.orchestrator.matrix_execution import MatrixExecutionError, execute_persisted_dc_matrix
from pvl.orchestrator.preflight import SolverRoute
from pvl.orchestrator.scientific_execution import exploratory_complete_rig_dc_mesh_profile
from pvl.rig.fingerprint import rig_definition_fingerprint


def _package(tmp_path: Path):
    rig = architecture_example_rig_v1()
    materials = load_builtin_material_library()
    config = ExperimentConfig(
        experiment_id="matrix-test",
        repetitions=1,
        randomization_seed=23,
        material_library_fingerprint=materials.fingerprint_sha256(),
        rig_definition_fingerprint=rig_definition_fingerprint(rig),
    )
    package = persist_dc_experiment_package(
        config,
        1.0,
        tmp_path,
        created_utc=datetime(2026, 8, 15, 0, 0, tzinfo=timezone.utc),
    )
    matrix = json.loads(Path(package.layout.run_matrix_json).read_text(encoding="utf-8"))
    return rig, materials, package, matrix


def _fake_result(results_root: Path, package, run_id: str, route: SolverRoute):
    root = (
        results_root
        / "matrix-test"
        / "executions"
        / package.manifest.package_id
        / run_id
        / "scientific"
        / f"science-{run_id[-4:]}"
    )
    root.mkdir(parents=True, exist_ok=True)
    return SimpleNamespace(
        root=str(root),
        manifest=SimpleNamespace(
            job_id=f"science-{run_id[-4:]}",
            job_fingerprint=("a" if route == SolverRoute.CONTROL else "b") * 64,
            solver_route=route,
            solver_execution=route == SolverRoute.MAGNETOSTATIC,
        ),
    )


def test_dc_matrix_executes_exact_persisted_randomized_order_sequentially(tmp_path: Path):
    rig, materials, package, matrix = _package(tmp_path)
    expected_order = [row["run_id"] for row in matrix]
    state_by_run = {row["run_id"]: row["state_id"] for row in matrix}
    calls: list[str] = []
    active_calls = 0
    maximum_active = 0

    def fake_executor(**kwargs):
        nonlocal active_calls, maximum_active
        run_id = kwargs["run_id"]
        active_calls += 1
        maximum_active = max(maximum_active, active_calls)
        calls.append(run_id)
        route = SolverRoute.CONTROL if state_by_run[run_id] == "off_off" else SolverRoute.MAGNETOSTATIC
        result = _fake_result(tmp_path, package, run_id, route)
        active_calls -= 1
        return result

    result = execute_persisted_dc_matrix(
        package_root=Path(package.layout.root),
        rig=rig,
        materials=materials,
        results_root=tmp_path,
        mesh_config=exploratory_complete_rig_dc_mesh_profile(),
        created_utc=datetime(2026, 8, 15, 1, 0, tzinfo=timezone.utc),
        single_run_executor=fake_executor,
    )

    assert calls == expected_order
    assert maximum_active == 1
    assert [record.run_id for record in result.manifest.runs] == expected_order
    assert [record.sequence_index for record in result.manifest.runs] == list(range(len(matrix)))
    assert result.manifest.run_count == len(matrix)
    assert result.manifest.completed_run_count == len(matrix)
    assert result.manifest.sequential_execution is True
    assert result.manifest.max_concurrent_solver_jobs == 1
    assert result.manifest.randomized_plan_order_preserved is True
    assert result.manifest.biological_testing is False
    assert result.manifest.hypothesis_analysis is False
    assert result.manifest.physical_validation is False
    root = Path(result.root)
    assert (root / "matrix_manifest.json").is_file()
    assert (root / "progress.json").is_file()
    assert (root / "checksums.json").is_file()


def test_dc_matrix_failure_preserves_completed_progress_evidence(tmp_path: Path):
    rig, materials, package, matrix = _package(tmp_path)
    state_by_run = {row["run_id"]: row["state_id"] for row in matrix}
    calls: list[str] = []

    def failing_executor(**kwargs):
        run_id = kwargs["run_id"]
        calls.append(run_id)
        if len(calls) == 3:
            raise RuntimeError("synthetic solver interruption")
        route = SolverRoute.CONTROL if state_by_run[run_id] == "off_off" else SolverRoute.MAGNETOSTATIC
        return _fake_result(tmp_path, package, run_id, route)

    with pytest.raises(MatrixExecutionError) as caught:
        execute_persisted_dc_matrix(
            package_root=Path(package.layout.root),
            rig=rig,
            materials=materials,
            results_root=tmp_path,
            mesh_config=exploratory_complete_rig_dc_mesh_profile(),
            single_run_executor=failing_executor,
        )
    assert caught.value.evidence_root is not None
    failed_root = Path(caught.value.evidence_root)
    failure = json.loads((failed_root / "failure.json").read_text(encoding="utf-8"))
    assert failure["completed_run_count"] == 2
    assert failure["run_count"] == len(matrix)
    assert failure["error_type"] == "RuntimeError"
    assert "synthetic solver interruption" in failure["error"]
    assert (failed_root / "progress.json").is_file()


def test_dc_matrix_identity_cannot_be_overwritten(tmp_path: Path):
    rig, materials, package, matrix = _package(tmp_path)
    state_by_run = {row["run_id"]: row["state_id"] for row in matrix}

    def fake_executor(**kwargs):
        run_id = kwargs["run_id"]
        route = SolverRoute.CONTROL if state_by_run[run_id] == "off_off" else SolverRoute.MAGNETOSTATIC
        return _fake_result(tmp_path, package, run_id, route)

    kwargs = dict(
        package_root=Path(package.layout.root),
        rig=rig,
        materials=materials,
        results_root=tmp_path,
        mesh_config=exploratory_complete_rig_dc_mesh_profile(),
        single_run_executor=fake_executor,
    )
    execute_persisted_dc_matrix(**kwargs)
    with pytest.raises(FileExistsError, match="already exists"):
        execute_persisted_dc_matrix(**kwargs)
