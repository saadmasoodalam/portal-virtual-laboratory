from pydantic import BaseModel
import pytest

from pvl.geometry.rig_compile import compile_rig_geometry
from pvl.rig.measurements import CoordinateMeasurement, CountMeasurement, LengthMeasurement, MeasurementStatus
from pvl.rig.schema import RigV1Schema


def _complete(rig):
    def fill(value):
        if isinstance(value, CoordinateMeasurement):
            value.value_m, value.status = 0.0, MeasurementStatus.ILLUSTRATIVE
        elif isinstance(value, LengthMeasurement):
            value.value_m, value.status = 0.1, MeasurementStatus.ILLUSTRATIVE
        elif isinstance(value, CountMeasurement):
            value.value, value.status = 10, MeasurementStatus.ILLUSTRATIVE
        elif isinstance(value, BaseModel):
            for name in value.__class__.model_fields:
                fill(getattr(value, name))
        elif isinstance(value, list):
            for item in value:
                fill(item)
    fill(rig)
    rig.sample_chamber.wall_thickness.value_m = 0.01
    return rig


def test_incomplete_rig_does_not_compile():
    with pytest.raises(ValueError):
        compile_rig_geometry(RigV1Schema())


def test_complete_rig_compiles_expected_core_components():
    manifest = compile_rig_geometry(_complete(RigV1Schema()))
    ids = {item.component_id for item in manifest.components}
    assert ids == {"steel_frame", "copper_boundary", "sample_chamber_wall", "sample_medium", "coil_a", "coil_b"}
    assert len(manifest.fingerprint_sha256()) == 64


def test_manifest_is_deterministic_for_same_geometry():
    first = compile_rig_geometry(_complete(RigV1Schema()))
    second = compile_rig_geometry(_complete(RigV1Schema()))
    assert first.fingerprint_sha256() == second.fingerprint_sha256()
