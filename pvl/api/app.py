from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict

from pvl.experiments.models import (
    BoundaryCircuitState,
    ExperimentConfig,
    ExperimentPurpose,
    SampleMedium,
    SolverFidelity,
)
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
    physics_state_hash: str
    solver_execution: bool = False
    experiment: ExperimentConfig


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
        """Return the canonical empty Rig v1 manifest without inventing dimensions."""
        return RigV1Schema()

    @application.get("/api/v1/materials", response_model=MaterialCatalogResponse)
    def material_catalog() -> MaterialCatalogResponse:
        """Return the versioned material choices available to the controlled Rig editor."""
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
        """Create a solver-disabled experiment draft tied to the exact Rig and material-library fingerprints."""
        return _experiment_template(rig, library)

    @application.post("/api/v1/experiment/validate", response_model=ExperimentValidationResponse)
    def experiment_validate(experiment: ExperimentConfig) -> ExperimentValidationResponse:
        """Validate the declared experiment state without scheduling or executing a solver."""
        return ExperimentValidationResponse(
            physics_state_hash=experiment.physics_state_hash(),
            experiment=experiment,
        )

    return application


app = create_app()
