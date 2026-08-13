import pytest

from pvl.rig.measurements import LengthMeasurement, MeasurementStatus
from pvl.rig.models import RigV1Definition


def test_unknown_measurement_cannot_hide_a_numeric_value():
    with pytest.raises(ValueError):
        LengthMeasurement(value_m=0.1, status=MeasurementStatus.UNKNOWN)


def test_illustrative_measurement_is_computational_but_not_hardware_fidelity():
    measurement = LengthMeasurement(value_m=0.1, status=MeasurementStatus.ILLUSTRATIVE)
    assert measurement.has_value
    assert not measurement.is_hardware_fidelity


def test_default_rig_contains_no_invented_physical_dimensions():
    rig = RigV1Definition()
    report = rig.readiness_report()
    assert not report.computational_ready
    assert not report.hardware_fidelity_ready
    assert report.missing_required_measurements
    assert not report.non_fidelity_measurements


def test_default_boundary_preserves_open_isolated_baseline():
    rig = RigV1Definition()
    assert rig.copper_boundary.baseline_open_loop
    assert rig.copper_boundary.electrically_isolated_from_frame
