from pydantic import BaseModel

from pvl.geometry.provenance import compilation_record
from pvl.geometry.rig_compile import compile_rig_geometry
from pvl.rig.fingerprint import rig_definition_fingerprint
from pvl.rig.measurements import CoordinateMeasurement, CountMeasurement, LengthMeasurement, MeasurementStatus
from pvl.rig.schema import RigV1Schema


def _fill(value):
    if isinstance(value, CoordinateMeasurement):
        value.value_m, value.status = 0.0, MeasurementStatus.ILLUSTRATIVE
    elif isinstance(value, LengthMeasurement):
        value.value_m, value.status = 0.1, MeasurementStatus.ILLUSTRATIVE
    elif isinstance(value, CountMeasurement):
        value.value, value.status = 10, MeasurementStatus.ILLUSTRATIVE
    elif isinstance(value, BaseModel):
        for name in value.__class__.model_fields:
            _fill(getattr(value, name))
    elif isinstance(value, list):
        for item in value:
            _fill(item)


def test_compilation_record_links_source_and_geometry_hashes():
    rig = RigV1Schema()
    _fill(rig)
    rig.sample_chamber.wall_thickness.value_m = 0.01
    geometry = compile_rig_geometry(rig)
    record = compilation_record(rig, geometry)
    assert record.rig_fingerprint == rig_definition_fingerprint(rig)
    assert record.geometry_fingerprint == geometry.fingerprint_sha256()
