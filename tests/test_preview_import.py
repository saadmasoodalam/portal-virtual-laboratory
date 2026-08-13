from pvl.geometry.adapter import GeometryAdapterMode, adapter_status
from pvl.geometry.preview import PreviewFidelity, build_preview_scene
from pvl.geometry.rig_manifest import GeometryComponent, RigGeometryManifest, RigShape
from pvl.materials.library import load_builtin_material_library
from pvl.rig.schema import RigV1Schema


def test_preview_module_marks_scene_non_solver():
    item = GeometryComponent(
        component_id="sample",
        shape=RigShape.CYLINDRICAL_VOLUME,
        material_id="air_baseline",
        center_m=(0.0, 0.0, 0.0),
        parameters_m={"radius": 0.02, "height": 0.05},
    )
    scene = build_preview_scene(RigGeometryManifest(rig_id="example", components=(item,)))
    assert scene.fidelity == PreviewFidelity.ILLUSTRATIVE
    assert scene.solver_mesh is False
    assert scene.items[0].component_id == "sample"


def test_preview_adapter_rejects_unknown_required_measurements():
    status = adapter_status(
        RigV1Schema(), load_builtin_material_library(), GeometryAdapterMode.PREVIEW
    )
    assert not status.ready
    assert "required_geometry_measurements_missing" in status.reasons
