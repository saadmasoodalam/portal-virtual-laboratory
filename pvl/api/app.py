from __future__ import annotations

from hashlib import sha256
import json

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
from pvl.experiments.planning import plan_rig_v1_dc_experiment
from pvl.geometry.adapter import GeometryAdapterMode, adapter_status, build_preview_from_rig
from pvl.geometry.preview import PreviewScene
from pvl.materials.library import MaterialLibrary, load_builtin_material_library
from pvl.materials.models import MaterialCategory, MaterialDataStatus, MaterialModelKind
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


def _plan_hash(runs: tuple[DcPlannedRunResponse, ...]) -> str:
    payload = [run.model_dump(mode="json") for run in runs]
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return sha256(canonical.encode("utf-8")).hexdigest()


def create_app(materials: MaterialLibrary | None = None) -> FastAPI:
    library = materials or load_builtin_material_library()
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
            plan_hash=_plan_hash(runs),
            current_a=request.current_a,
            run_count=len(runs),
            repetitions=request.experiment.repetitions,
            randomization_seed=request.experiment.randomization_seed,
            runs=runs,
        )

    return application


app = create_app()
