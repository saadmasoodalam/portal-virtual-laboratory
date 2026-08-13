import pytest

from pvl.rig.measurements import CoordinateMeasurement, LengthMeasurement, MeasurementStatus
from pvl.rig.schema import RigV1Schema


def test_unknown_measurement_cannot_hide_a_numeric_value():
    with pytest.raises(ValueError):
        LengthMeasurement(value_m=0.1, status=MeasurementStatus.UNKNOWN)


def test_coordinates_allow_zero_and_negative_positions():
    zero = CoordinateMeasurement(value_m=0.0, status=MeasurementStatus.MEASURED)
    negative = CoordinateMeasurement(value_m=-0.025, status=MeasurementStatus.MEASURED)
    assert zero.has_value and negative.has_value


def test_illustrative_measurement_is_not_hardware_fidelity():
    measurement = LengthMeasurement(value_m=0.1, status=MeasurementStatus.ILLUSTRATIVE)
    assert measurement.has_value
    assert not measurement.is_hardware_fidelity


def test_default_schema_contains_no_invented_dimensions():
    rig = RigV1Schema()
    report = rig.readiness_report()
    assert not report.computational_ready
    assert not report.hardware_fidelity_ready
    assert report.missing_required_measurements
    assert not report.non_fidelity_measurements


def test_default_boundary_preserves_open_isolated_baseline():
    rig = RigV1Schema()
    assert rig.copper_boundary.baseline_open_loop
    assert rig.copper_boundary.electrically_isolated_from_frame
