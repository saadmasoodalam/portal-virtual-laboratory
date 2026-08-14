from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from pvl.experiments.models import (
    BoundaryCircuitState,
    CoilDriveState,
    ExperimentConfig,
    ExperimentPurpose,
    SampleMedium,
    SolverFidelity,
)
from pvl.experiments.package import experiment_plan_hash, persist_dc_experiment_package
from pvl.experiments.planning import plan_rig_v1_dc_experiment
from pvl.geometry.adapter import GeometryAdapterMode, adapter_status, build_preview_from_rig
from pvl.geometry.preview import PreviewScene
from pvl.materials.library import MaterialLibrary, load_builtin_material_library
from pvl.materials.models import MaterialCategory, MaterialDataStatus, MaterialModelKind
from pvl.orchestrator.execution import (
    ExecutionGateIssue,
    PackageIntegrityError,
    PlannedRunNotFoundError,
    evaluate_and_persist_single_run_gate,
)
from pvl.orchestrator.preflight import SolverRoute
from pvl.rig.fingerprint import rig_definition_fingerprint
from pvl.rig.schema import ReadinessReport, RigV1Schema


class PreviewProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    api_version: str = "pvl-preview-v1"
    material_library_version: str
    material_library_fingerprint: str


class PreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    readiness: ReadinessReport
    provenance: PreviewProvenance
    scene: PreviewScene


class MaterialCatalogItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    material_id: str
    display_name: str
    category: MaterialCategory
    model_kind: MaterialModelKind
    provenance_status: MaterialDataStatus
    hardware_fidelity_data: bool
    solver_warning: str


class MaterialCatalogResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    library_version: str
    library_fingerprint: str
    materials: tuple[MaterialCatalogItem, ...]


class ExperimentValidationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    accepted: bool = True
    configuration_hash: str
    physics_state_hash: str
    solver_execution: bool = False
    experiment: ExperimentConfig


class DcPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    experiment: ExperimentConfig
    current_a: float = Field(gt=0.0)


class DcPlannedRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    run_id: str
    sequence_index: int
    repetition_index: int
    state_id: str
    configuration_hash: str
    physics_state_hash: str
    coil_a: CoilDriveState
    coil_b: CoilDriveState


class DcPlanResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    plan_hash: str
    current_a: float
    run_count: int
    repetitions: int
    randomization_seed: int
    solver_execution: bool = False
    runs: tuple[DcPlannedRunResponse, ...]


class ExperimentPackageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    package_id: str
    plan_hash: str
    package_fingerprint: str
    configuration_hash: str
    physics_state_hash: str
    run_count: int
    relative_path: str
    checksummed_files: int
    solver_execution: bool = False


class SingleRunGateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    experiment_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    package_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    run_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    rig: RigV1Schema
    single_run_confirmation: Literal[True]


class SingleRunGateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    job_id: str
    job_fingerprint: str
    package_id: str
    run_id: str
    solver_route: SolverRoute
    package_integrity_verified: bool
    preflight_ready: bool
    execution_allowed: bool
    solver_execution: bool
    single_run_only: bool
    batch_execution: bool
    biological_testing: bool
    issues: tuple[ExecutionGateIssue, ...]
    relative_execution_path: str


def _experiment_medium(rig: RigV1Schema) -> SampleMedium:
    by_material = {medium.material_id: medium for medium in SampleMedium}
    try:
        return by_material[rig.sample_chamber.medium_material_id]
    except KeyError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "experiment_medium_unsupported",
                "material_id": rig.sample_chamber.medium_material_id,
                "supported_material_ids": sorted(by_material),
            },
        ) from exc


def _experiment_template(rig: RigV1Schema, library: MaterialLibrary) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_id="experiment-001",
        rig_id=rig.rig_id,
        purpose=ExperimentPurpose.BASELINE,
        medium=_experiment_medium(rig),
        copper_boundary_state=(
            BoundaryCircuitState.OPEN if rig.copper_boundary.baseline_open_loop else BoundaryCircuitState.CLOSED
        ),
        duration_s=60.0,
        repetitions=3,
        randomization_seed=0,
        solver_fidelity=SolverFidelity.EXPLORATORY,
        material_library_fingerprint=library.fingerprint_sha256(),
        rig_definition_fingerprint=rig_definition_fingerprint(rig),
    )


def create_app(materials: MaterialLibrary | None = None, results_root: Path | None = None) -> FastAPI:
    library = materials or load_builtin_material_library()
    storage_root = results_root or Path("results")
    application = FastAPI(title="PVL API", version="0.1.0")

    @application.get("/api/v1/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "api_version": "pvl-preview-v1",
            "scope": "preview_geometry_only",
            "solver_execution": False,
        }

    @application.get("/api/v1/rig/template", response_model=RigV1Schema)
    def rig_template() -> RigV1Schema:
        return RigV1Schema()

    @application.get("/api/v1/materials", response_model=MaterialCatalogResponse)
    def material_catalog() -> MaterialCatalogResponse:
        items: list[MaterialCatalogItem] = []
        for material_id in library.ids():
            record = library.require(material_id)
            items.append(
                MaterialCatalogItem(
                    material_id=record.material_id,
                    display_name=record.display_name,
                    category=record.category,
                    model_kind=record.model_kind,
                    provenance_status=record.provenance.status,
                    hardware_fidelity_data=record.is_hardware_fidelity_data,
                    solver_warning=record.solver_warning,
                )
            )
        return MaterialCatalogResponse(
            library_version=library.version,
            library_fingerprint=library.fingerprint_sha256(),
            materials=tuple(items),
        )

    @application.post("/api/v1/rig/preview", response_model=PreviewResponse)
    def rig_preview(rig: RigV1Schema) -> PreviewResponse:
        readiness = rig.readiness_report()
        status = adapter_status(rig, library, GeometryAdapterMode.PREVIEW)
        if not status.ready:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "preview_not_ready",
                    "reasons": list(status.reasons),
                    "readiness": readiness.model_dump(mode="json"),
                },
            )
        return PreviewResponse(
            readiness=readiness,
            provenance=PreviewProvenance(
                material_library_version=library.version,
                material_library_fingerprint=library.fingerprint_sha256(),
            ),
            scene=build_preview_from_rig(rig, library),
        )

    @application.post("/api/v1/experiment/template", response_model=ExperimentConfig)
    def experiment_template(rig: RigV1Schema) -> ExperimentConfig:
        return _experiment_template(rig, library)

    @application.post("/api/v1/experiment/validate", response_model=ExperimentValidationResponse)
    def experiment_validate(experiment: ExperimentConfig) -> ExperimentValidationResponse:
        return ExperimentValidationResponse(
            configuration_hash=experiment.configuration_hash(),
            physics_state_hash=experiment.physics_state_hash(),
            experiment=experiment,
        )

    @application.post("/api/v1/experiment/plan/dc", response_model=DcPlanResponse)
    def experiment_plan_dc(request: DcPlanRequest) -> DcPlanResponse:
        planned = plan_rig_v1_dc_experiment(request.experiment, request.current_a)
        runs = tuple(
            DcPlannedRunResponse(
                run_id=run.run_id,
                sequence_index=run.sequence_index,
                repetition_index=run.repetition_index,
                state_id=run.state_id,
                configuration_hash=run.configuration.configuration_hash(),
                physics_state_hash=run.configuration.physics_state_hash(),
                coil_a=run.configuration.coil_a,
                coil_b=run.configuration.coil_b,
            )
            for run in planned
        )
        return DcPlanResponse(
            plan_hash=experiment_plan_hash(planned),
            current_a=request.current_a,
            run_count=len(runs),
            repetitions=request.experiment.repetitions,
            randomization_seed=request.experiment.randomization_seed,
            runs=runs,
        )

    @application.post("/api/v1/experiment/plan/dc/persist", response_model=ExperimentPackageResponse)
    def experiment_persist_dc(request: DcPlanRequest) -> ExperimentPackageResponse:
        try:
            package = persist_dc_experiment_package(
                request.experiment,
                request.current_a,
                storage_root,
            )
        except FileExistsError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "experiment_package_exists", "message": str(exc)},
            ) from exc
        return ExperimentPackageResponse(
            package_id=package.manifest.package_id,
            plan_hash=package.manifest.plan_hash,
            package_fingerprint=package.manifest.package_fingerprint,
            configuration_hash=package.manifest.configuration_hash,
            physics_state_hash=package.manifest.physics_state_hash,
            run_count=package.manifest.run_count,
            relative_path=str(Path(package.layout.root).relative_to(storage_root)),
            checksummed_files=len(package.checksums),
        )

    @application.post("/api/v1/experiment/execution/single/gate", response_model=SingleRunGateResponse)
    def experiment_single_run_gate(request: SingleRunGateRequest) -> SingleRunGateResponse:
        package_root = storage_root / request.experiment_id / "packages" / request.package_id
        try:
            result = evaluate_and_persist_single_run_gate(
                package_root=package_root,
                run_id=request.run_id,
                rig=request.rig,
                materials=library,
                results_root=storage_root,
            )
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail={"code": "experiment_package_not_found", "message": str(exc)},
            ) from exc
        except PlannedRunNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail={"code": "planned_run_not_found", "message": str(exc)},
            ) from exc
        except PackageIntegrityError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "experiment_package_integrity_failed", "message": str(exc)},
            ) from exc
        except FileExistsError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "single_run_gate_exists", "message": str(exc)},
            ) from exc
        manifest = result.manifest
        return SingleRunGateResponse(
            job_id=manifest.job_id,
            job_fingerprint=manifest.job_fingerprint,
            package_id=manifest.package_id,
            run_id=manifest.run_id,
            solver_route=manifest.solver_route,
            package_integrity_verified=manifest.package_integrity_verified,
            preflight_ready=manifest.preflight_ready,
            execution_allowed=manifest.execution_allowed,
            solver_execution=manifest.solver_execution,
            single_run_only=manifest.single_run_only,
            batch_execution=manifest.batch_execution,
            biological_testing=manifest.biological_testing,
            issues=manifest.issues,
            relative_execution_path=str(Path(result.root).relative_to(storage_root)),
        )

    return application


app = create_app()
