from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import shutil
from uuid import uuid4

from pvl.sweeps.dc import DcSweepPlan


@dataclass(frozen=True)
class PersistedDcSweepPlan:
    root: Path
    plan_path: Path
    manifest_path: Path
    checksums_path: Path
    checksums: dict[str, str]


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _collect(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): _file_sha256(path)
        for path in sorted(item for item in root.rglob("*") if item.is_file() and item.name != "checksums.json")
    }


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def persist_dc_sweep_plan(plan: DcSweepPlan, results_root: Path) -> PersistedDcSweepPlan:
    """Persist a sweep plan atomically without executing any solver.

    The complete point records intentionally include their Rig and Experiment snapshots. This makes
    a material-medium or open/closed topology change auditable rather than leaving it as an external
    label that could later drift away from the constructive geometry.
    """
    final_root = results_root / plan.sweep_id / "sweeps" / plan.sweep_hash
    if final_root.exists():
        raise FileExistsError(f"DC sweep package already exists: {plan.sweep_hash}")
    final_root.parent.mkdir(parents=True, exist_ok=True)
    staging = final_root.parent / f".{plan.sweep_hash}.staging-{uuid4().hex}"
    try:
        staging.mkdir(parents=True, exist_ok=False)
        plan_path = staging / "plan.json"
        manifest_path = staging / "manifest.json"
        _write_json(plan_path, plan.model_dump(mode="json"))
        _write_json(
            manifest_path,
            {
                "schema_version": plan.schema_version,
                "sweep_id": plan.sweep_id,
                "sweep_hash": plan.sweep_hash,
                "point_count": plan.point_count,
                "solver_execution": False,
                "hypothesis_analysis": False,
                "point_hashes": [point.point_hash for point in plan.points],
                "scientific_boundary": (
                    "Immutable deterministic sweep planning only. No FEM solver result, anomaly "
                    "classification or Portal Hypothesis output is created by this package."
                ),
            },
        )
        checksums = _collect(staging)
        checksums_path = staging / "checksums.json"
        _write_json(checksums_path, checksums)
        staging.rename(final_root)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return PersistedDcSweepPlan(
        root=final_root,
        plan_path=final_root / "plan.json",
        manifest_path=final_root / "manifest.json",
        checksums_path=final_root / "checksums.json",
        checksums=checksums,
    )


def verify_dc_sweep_plan(root: Path) -> bool:
    try:
        expected = json.loads((root / "checksums.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(expected, dict) and expected == _collect(root)
