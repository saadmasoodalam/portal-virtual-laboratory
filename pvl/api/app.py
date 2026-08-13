from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict

from pvl.geometry.adapter import GeometryAdapterMode, adapter_status, build_preview_from_rig
from pvl.geometry.preview import PreviewScene
from pvl.materials.library import MaterialLibrary, load_builtin_material_library
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

    return application


app = create_app()
