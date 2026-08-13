from pvl.geometry.preview import PreviewFidelity, build_preview_scene
from pvl.geometry.rig_manifest import GeometryComponent, RigGeometryManifest, RigShape


def test_preview_module_imports_and_marks_scene_non_solver():
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
