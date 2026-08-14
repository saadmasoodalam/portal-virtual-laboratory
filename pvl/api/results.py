from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from pvl.orchestrator.execution import PackageIntegrityError, _collect_checksums
from pvl.orchestrator.scientific_execution import ScientificRunManifest


class ScientificRunSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    experiment_id: str
    package_id: str
    run_id: str
    job_id: str
    solver_route: str
    solver_execution: bool
    geometry_fidelity: str
    mesh_configuration_hash: str
    created_utc: str
    checksum_verified: bool = True
    hypothesis_analysis: bool
    physical_validation: bool
    relative_path: str


class ScientificRunCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    experiment_id: str
    runs: tuple[ScientificRunSummary, ...]


class ScientificRunDetail(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    summary: ScientificRunSummary
    metrics: dict[str, float]
    solver_metadata: dict[str, object]
    experiment_metadata: dict[str, object]


def _safe_identifier(value: str, label: str) -> str:
    if not value or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for character in value):
        raise HTTPException(status_code=422, detail={"code": "invalid_identifier", "field": label})
    return value


def _read_object(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PackageIntegrityError(f"cannot read scientific result JSON: {path.name}") from exc
    if not isinstance(value, dict):
        raise PackageIntegrityError(f"scientific result JSON is not an object: {path.name}")
    return value


def _verified_run(root: Path, results_root: Path, experiment_id: str) -> ScientificRunSummary:
    manifest_path = root / "job_manifest.json"
    checksum_path = root / "checksums.json"
    if not manifest_path.is_file() or not checksum_path.is_file():
        raise PackageIntegrityError("scientific run manifest/checksum file missing")
    manifest = ScientificRunManifest.model_validate(_read_object(manifest_path))
    expected = _read_object(checksum_path)
    actual = _collect_checksums(root)
    if actual != expected:
        raise PackageIntegrityError(f"scientific result checksum verification failed: {manifest.job_id}")
    return ScientificRunSummary(
        experiment_id=experiment_id,
        package_id=manifest.package_id,
        run_id=manifest.run_id,
        job_id=manifest.job_id,
        solver_route=manifest.solver_route.value,
        solver_execution=manifest.solver_execution,
        geometry_fidelity=manifest.geometry_fidelity,
        mesh_configuration_hash=manifest.mesh_configuration_hash,
        created_utc=manifest.created_utc.isoformat(),
        hypothesis_analysis=manifest.hypothesis_analysis,
        physical_validation=manifest.physical_validation,
        relative_path=str(root.relative_to(results_root)),
    )


def list_verified_scientific_runs(results_root: Path, experiment_id: str) -> ScientificRunCatalog:
    experiment_id = _safe_identifier(experiment_id, "experiment_id")
    base = results_root / experiment_id / "executions"
    if not base.is_dir():
        return ScientificRunCatalog(experiment_id=experiment_id, runs=())
    summaries: list[ScientificRunSummary] = []
    for manifest_path in sorted(base.glob("*/*/scientific/*/job_manifest.json")):
        try:
            summaries.append(_verified_run(manifest_path.parent, results_root, experiment_id))
        except (PackageIntegrityError, ValueError):
            # Corrupt/incomplete records are intentionally excluded from the trusted catalog. The
            # explicit detail endpoint returns an integrity error when one is addressed directly.
            continue
    summaries.sort(key=lambda item: (item.created_utc, item.run_id, item.job_id), reverse=True)
    return ScientificRunCatalog(experiment_id=experiment_id, runs=tuple(summaries))


def read_verified_scientific_run(
    results_root: Path,
    experiment_id: str,
    package_id: str,
    run_id: str,
    job_id: str,
) -> ScientificRunDetail:
    values = [
        _safe_identifier(experiment_id, "experiment_id"),
        _safe_identifier(package_id, "package_id"),
        _safe_identifier(run_id, "run_id"),
        _safe_identifier(job_id, "job_id"),
    ]
    experiment_id, package_id, run_id, job_id = values
    root = (
        results_root
        / experiment_id
        / "executions"
        / package_id
        / run_id
        / "scientific"
        / job_id
    )
    if not root.is_dir():
        raise FileNotFoundError(f"scientific result not found: {job_id}")
    summary = _verified_run(root, results_root, experiment_id)
    if summary.package_id != package_id or summary.run_id != run_id or summary.job_id != job_id:
        raise PackageIntegrityError("scientific result path does not match signed manifest identity")
    metrics_payload = _read_object(root / "metrics.json")
    metrics_value = metrics_payload.get("metrics", {})
    if not isinstance(metrics_value, dict):
        raise PackageIntegrityError("scientific result metrics payload is invalid")
    metrics: dict[str, float] = {}
    for key, value in metrics_value.items():
        if isinstance(key, str) and isinstance(value, (int, float)) and not isinstance(value, bool):
            metrics[key] = float(value)
    return ScientificRunDetail(
        summary=summary,
        metrics=metrics,
        solver_metadata=_read_object(root / "solver.json"),
        experiment_metadata=_read_object(root / "experiment.json"),
    )


def build_results_router(*, results_root: Path) -> APIRouter:
    router = APIRouter(prefix="/api/v1/results", tags=["results"])

    @router.get("/{experiment_id}", response_model=ScientificRunCatalog)
    def result_catalog(experiment_id: str) -> ScientificRunCatalog:
        return list_verified_scientific_runs(results_root, experiment_id)

    @router.get(
        "/{experiment_id}/{package_id}/{run_id}/{job_id}",
        response_model=ScientificRunDetail,
    )
    def result_detail(
        experiment_id: str,
        package_id: str,
        run_id: str,
        job_id: str,
    ) -> ScientificRunDetail:
        try:
            return read_verified_scientific_run(
                results_root,
                experiment_id,
                package_id,
                run_id,
                job_id,
            )
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail={"code": "scientific_result_not_found", "message": str(exc)},
            ) from exc
        except PackageIntegrityError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "scientific_result_integrity_failed", "message": str(exc)},
            ) from exc

    return router
