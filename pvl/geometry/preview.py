from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from pvl.geometry.bounds import component_bounds, manifest_bounds
from pvl.geometry.rig_manifest import GeometryComponent, RigGeometryManifest, RigShape


class PreviewFidelity(StrEnum):
    ILLUSTRATIVE = "illustrative_geometry"


class PreviewPrimitive(StrEnum):
    BOX_ENVELOPE = "box_envelope"
    OPEN_RECTANGULAR_LOOP = "open_rectangular_loop"
    CYLINDER_SHELL = "cylinder_shell"
    CYLINDER = "cylinder"
    WINDING_ENVELOPE = "winding_envelope"
    POINT = "point"


class PreviewItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    component_id: str
    primitive: PreviewPrimitive
    material_id: str | None
    center_m: tuple[float, float, float]
    axis: tuple[float, float, float] | None = None
    parameters_m: dict[str, float]
    integer_parameters: dict[str, int] = Field(default_factory=dict)
    metadata: dict[str, str | bool] = Field(default_factory=dict)
    bounds_min_m: tuple[float, float, float]
    bounds_max_m: tuple[float, float, float]


class PreviewScene(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    rig_id: str
    geometry_fingerprint: str
    fidelity: PreviewFidelity = PreviewFidelity.ILLUSTRATIVE
    solver_mesh: bool = False
    world_bounds_min_m: tuple[float, float, float]
    world_bounds_max_m: tuple[float, float, float]
    items: tuple[PreviewItem, ...]


def _primitive(shape: RigShape) -> PreviewPrimitive:
    mapping = {
        RigShape.FRAME_ENVELOPE: PreviewPrimitive.BOX_ENVELOPE,
        RigShape.OPEN_RECTANGULAR_LOOP: PreviewPrimitive.OPEN_RECTANGULAR_LOOP,
        RigShape.CYLINDRICAL_SHELL: PreviewPrimitive.CYLINDER_SHELL,
        RigShape.CYLINDRICAL_VOLUME: PreviewPrimitive.CYLINDER,
        RigShape.WINDING_ENVELOPE: PreviewPrimitive.WINDING_ENVELOPE,
        RigShape.SENSOR_POINT: PreviewPrimitive.POINT,
    }
    return mapping[shape]


def _item(component: GeometryComponent) -> PreviewItem:
    bounds = component_bounds(component)
    return PreviewItem(
        component_id=component.component_id,
        primitive=_primitive(component.shape),
        material_id=component.material_id,
        center_m=component.center_m,
        axis=component.axis,
        parameters_m=dict(component.parameters_m),
        integer_parameters=dict(component.integer_parameters),
        metadata=dict(component.metadata),
        bounds_min_m=bounds.minimum_m,
        bounds_max_m=bounds.maximum_m,
    )


def build_preview_scene(manifest: RigGeometryManifest) -> PreviewScene:
    """Build a frontend-ready scene description without claiming solver-mesh fidelity."""
    world = manifest_bounds(manifest)
    return PreviewScene(
        rig_id=manifest.rig_id,
        geometry_fingerprint=manifest.fingerprint_sha256(),
        world_bounds_min_m=world.minimum_m,
        world_bounds_max_m=world.maximum_m,
        items=tuple(_item(component) for component in manifest.components),
    )
