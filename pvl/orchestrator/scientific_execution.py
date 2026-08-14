from __future__ import annotations

from datetime import datetime, timezone
import csv
import json
from pathlib import Path
import shutil
from typing import Callable, Literal
from uuid import uuid4

from pydantic import Field, model_validator

from pvl.core.models import FrozenModel
from pvl.experiments.models import ExperimentConfig
from pvl.geometry.constructive import compile_constructive_topology
from pvl.geometry.gmsh_rig import RigGmshConfig
from pvl.materials.library import MaterialLibrary
from pvl.orchestrator.execution import (
    EnvironmentMetadata,
    PackageIntegrityError,
    PlannedRunNotFoundError,
    _canonical_sha256,
    _capture_environment,
    _collect_checksums,
    _selected_run_configuration,
    _validate_package_identity,
    _write_json,
)
from pvl.orchestrator.preflight import SolverRoute, preflight_experiment
from pvl.rig.fingerprint import rig_definition_fingerprint
from pvl.rig.schema import RigV1Schema
from pvl.solvers.getdp.rig_magnetostatic_run import (
    RigMagnetostaticResult,
    run_complete_rig_dc_magnetostatic,
)
from pvl.solvers.getdp.runner import ExecutableSet


SCIENTIFIC_EXECUTION_SCHEMA_VERSION = "pvl-scientific-single-run-v1"


class ScientificExecutionBlockedError(RuntimeError):
    """Raised when a selected immutable run is not eligible for the requested solver route."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class ScientificRunManifest(FrozenModel):
    schema_version: Literal["pvl-scientific-single-run-v1"] = SCIENTIFIC_EXECUTION_SCHEMA_VERSION
    job_id: str
    job_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    package_id: str
    package_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    plan_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_id: str
    planned_configuration_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    physics_state_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    rig_definition_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    material_library_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    constructive_topology_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    solver_route: SolverRoute
    created_utc: datetime
    package_integrity_verified: Literal[True] = True
    preflight_ready: Literal[True] = True
    execution_allowed: Literal[True] = True
    solver_execution: bool
    single_run_only: Literal[True] = True
    batch_execution: Literal[False] = False
    biological_testing: Literal[False] = False
    hypothesis_analysis: Literal[False] = False
    physical_validation: Literal[False] = False
    geometry_fidelity: str
    mesh_configuration_hash: str
    solver_versions: dict[str, str] = Field(default_factory=dict)
    raw_directory: str = "raw"
    metrics_file: str = "metrics.json"
    summary_file: str = "summary.csv"

    @model_validator(mode="after")
    def require_utc_timestamp(self) -> "ScientificRunManifest":
        if self.created_utc.tzinfo is None or self.created_utc.utcoffset() != timezone.utc.utcoffset(self.created_utc):
            raise ValueError("created_utc must be timezone-aware UTC")
        if self.solver_route == SolverRoute.MAGNETOSTATIC and not self.solver_execution:
            raise ValueError("a persisted magnetostatic scientific run must record solver execution")
        if self.solver_route == SolverRoute.CONTROL and self.solver_execution:
            raise ValueError("an OFF/OFF control must not claim FEM solver execution")
        return self


class PersistedScientificRun(FrozenModel):
    root: str
    manifest: ScientificRunManifest
    checksums: dict[str, str]


MagnetostaticRunner = Callable[..., RigMagnetostaticResult]


def exploratory_complete_rig_dc_mesh_profile() -> RigGmshConfig:
    """Return the retained PVL-2Q exploratory complete-Rig DC mesh profile.

    This profile is versioned in code so a scientific run cannot silently inherit UI/default mesh
    values. PVL-2Q convergence remains the release gate for treating this profile as numerically
    validated; this function merely makes the proposed profile explicit and hashable.
    """
    return RigGmshConfig(
        characteristic_length_m=0.012,
        minimum_characteristic_length_m=0.001,
        air_margin_fraction=1.00,
        winding_characteristic_length_m=0.002,
        steel_characteristic_length_m=0.005,
        far_field_characteristic_length_m=0.040,
        far_field_near_margin_fraction=0.25,
        far_field_transition_m=0.10,
    )


def _materials_payload(materials: MaterialLibrary) -> dict[str, object]:
    return {
        "library_version": materials.version,
        "library_fingerprint": materials.fingerprint_sha256(),
        "materials": [
            materials.require(material_id).model_dump(mode="json")
            for material_id in materials.ids()
        ],
    }


def _summary_rows(metrics: dict[str, float]) -> list[tuple[str, float, str]]:
    units = {
        "axis_peak_abs_b_t": "T",
        "axis_rms_b_t": "T",
        "axis_center_b_y_t": "T",
        "probe_peak_abs_b_t": "T",
        "probe_center_b_y_t": "T",
    }
    return [(name, float(metrics[name]), units.get(name, "1")) for name in sorted(metrics)]


def _write_summary_csv(path: Path, metrics: dict[str, float]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("metric", "value", "unit"))
        writer.writerows(_summary_rows(metrics))


def _execution_fingerprint_payload(
    *,
    package_id: str,
    package_fingerprint: str,
    run_config: ExperimentConfig,
    topology_fingerprint: str,
    mesh_config: RigGmshConfig,
    solver_route: SolverRoute,
) -> dict[str, object]:
    return {
        "schema_version": SCIENTIFIC_EXECUTION_SCHEMA_VERSION,
        "package_id": package_id,
        "package_fingerprint": package_fingerprint,
        "run_id": run_config.experiment_id,
        "run_configuration_hash": run_config.configuration_hash(),
        "physics_state_hash": run_config.physics_state_hash(),
        "rig_definition_fingerprint": run_config.rig_definition_fingerprint,
        "material_library_fingerprint": run_config.material_library_fingerprint,
        "constructive_topology_fingerprint": topology_fingerprint,
        "solver_route": solver_route.value,
        "mesh_configuration_hash": mesh_config.configuration_hash(),
        "single_run_only": True,
        "batch_execution": False,
        "biological_testing": False,
        "hypothesis_analysis": False,
    }


def execute_and_persist_single_run(
    *,
    package_root: Path,
    run_id: str,
    rig: RigV1Schema,
    materials: MaterialLibrary,
    results_root: Path,
    mesh_config: RigGmshConfig,
    created_utc: datetime | None = None,
    executables: ExecutableSet | None = None,
    axis_samples: int = 101,
    probe_y_m: tuple[float, ...] = (-0.060, -0.030, 0.0, 0.030, 0.060),
    magnetostatic_runner: MagnetostaticRunner = run_complete_rig_dc_magnetostatic,
) -> PersistedScientificRun:
    """Execute exactly one trusted packaged control or DC magnetostatic state.

    The immutable experiment package is verified before and after execution. Active harmonic runs
    remain blocked until a complete-Rig magnetoquasistatic formulation receives its own validation
    gate. The Portal Hypothesis layer is not invoked and cannot modify any solver input or output.
    """
    package, base_config, matrix = _validate_package_identity(package_root)
    run_config = _selected_run_configuration(package_root, base_config, matrix, run_id)
    report = preflight_experiment(run_config, rig, materials)
    if not report.ready:
        codes = ",".join(issue.code for issue in report.issues) or "unknown_preflight_error"
        raise ScientificExecutionBlockedError(
            "preflight_not_ready",
            f"selected run failed scientific preflight: {codes}",
        )
    if report.solver_route not in {SolverRoute.CONTROL, SolverRoute.MAGNETOSTATIC}:
        raise ScientificExecutionBlockedError(
            "solver_route_not_validated",
            f"complete-Rig scientific execution is not validated for route: {report.solver_route.value}",
        )

    actual_rig_fingerprint = rig_definition_fingerprint(rig)
    if actual_rig_fingerprint != run_config.rig_definition_fingerprint:
        raise PackageIntegrityError("selected run Rig fingerprint changed after preflight")
    topology = compile_constructive_topology(rig)
    topology_fingerprint = topology.fingerprint_sha256()

    fingerprint = _canonical_sha256(
        _execution_fingerprint_payload(
            package_id=package.package_id,
            package_fingerprint=package.package_fingerprint,
            run_config=run_config,
            topology_fingerprint=topology_fingerprint,
            mesh_config=mesh_config,
            solver_route=report.solver_route,
        )
    )
    job_id = f"science-{fingerprint[:16]}"
    final_root = (
        results_root
        / package.experiment_id
        / "executions"
        / package.package_id
        / run_id
        / "scientific"
        / job_id
    )
    if final_root.exists():
        raise FileExistsError(f"scientific single-run execution already exists: {job_id}")
    final_root.parent.mkdir(parents=True, exist_ok=True)
    staging_root = final_root.parent / f".{job_id}.staging-{uuid4().hex}"
    captured = created_utc or datetime.now(timezone.utc)
    if captured.tzinfo is None or captured.utcoffset() != timezone.utc.utcoffset(captured):
        raise ValueError("created_utc must be timezone-aware UTC")

    environment: EnvironmentMetadata = _capture_environment(captured)
    solver_execution = False
    metrics: dict[str, float] = {}
    solver_version_map = dict(environment.solver_versions)

    try:
        staging_root.mkdir(parents=True, exist_ok=False)
        raw_root = staging_root / "raw"
        raw_root.mkdir()

        if report.solver_route == SolverRoute.MAGNETOSTATIC:
            result = magnetostatic_runner(
                run_config,
                topology,
                materials,
                mesh_config,
                raw_root,
                executables=executables,
                axis_samples=axis_samples,
                probe_y_m=probe_y_m,
            )
            solver_execution = True
            metrics = {name: float(value) for name, value in result.metrics.items()}
            solver_version_map = dict(result.solver_versions)

        _write_json(
            staging_root / "experiment.json",
            {
                "run_id": run_id,
                "configuration_hash": run_config.configuration_hash(),
                "physics_state_hash": run_config.physics_state_hash(),
                "configuration": run_config.model_dump(mode="json"),
            },
        )
        _write_json(
            staging_root / "geometry.json",
            {
                "rig_definition_fingerprint": actual_rig_fingerprint,
                "constructive_topology_fingerprint": topology_fingerprint,
                "geometry_fidelity": topology.geometry_fidelity,
                "rig": rig.model_dump(mode="json"),
                "constructive_topology": topology.model_dump(mode="json"),
            },
        )
        _write_json(staging_root / "materials.json", _materials_payload(materials))
        _write_json(
            staging_root / "solver.json",
            {
                "solver_route": report.solver_route.value,
                "solver_execution": solver_execution,
                "mesh_configuration": mesh_config.model_dump(mode="json"),
                "mesh_configuration_hash": mesh_config.configuration_hash(),
                "axis_samples": axis_samples,
                "probe_y_m": list(probe_y_m),
                "solver_versions": solver_version_map,
                "scientific_boundary": (
                    "Established-physics execution only. No Portal Hypothesis term, biological model, "
                    "or physical-validation claim is generated by this run."
                ),
            },
        )
        _write_json(staging_root / "environment.json", environment.model_dump(mode="json"))
        _write_json(
            staging_root / "metrics.json",
            {
                "solver_route": report.solver_route.value,
                "solver_execution": solver_execution,
                "metrics": metrics,
            },
        )
        _write_summary_csv(staging_root / "summary.csv", metrics)

        manifest = ScientificRunManifest(
            job_id=job_id,
            job_fingerprint=fingerprint,
            package_id=package.package_id,
            package_fingerprint=package.package_fingerprint,
            plan_hash=package.plan_hash,
            run_id=run_id,
            planned_configuration_hash=run_config.configuration_hash(),
            physics_state_hash=run_config.physics_state_hash(),
            rig_definition_fingerprint=run_config.rig_definition_fingerprint,
            material_library_fingerprint=run_config.material_library_fingerprint,
            constructive_topology_fingerprint=topology_fingerprint,
            solver_route=report.solver_route,
            created_utc=captured,
            solver_execution=solver_execution,
            geometry_fidelity=topology.geometry_fidelity,
            mesh_configuration_hash=mesh_config.configuration_hash(),
            solver_versions=solver_version_map,
        )
        _write_json(staging_root / "job_manifest.json", manifest.model_dump(mode="json"))
        checksums = _collect_checksums(staging_root)
        _write_json(staging_root / "checksums.json", checksums)
        staging_root.rename(final_root)
    except Exception:
        shutil.rmtree(staging_root, ignore_errors=True)
        raise

    from pvl.experiments.package import verify_experiment_package_checksums

    if not verify_experiment_package_checksums(package_root):
        raise PackageIntegrityError("immutable package changed during scientific execution")
    return PersistedScientificRun(root=str(final_root), manifest=manifest, checksums=checksums)
