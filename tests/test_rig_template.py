from pvl.rig.templates import build_rig_v1_measurement_template


def test_measurement_template_has_retained_sensor_roles_without_dimensions():
    rig = build_rig_v1_measurement_template()
    assert {sensor.sensor_id for sensor in rig.sensors} == {
        "magnetic_primary",
        "temperature_sample",
        "pickup_primary",
        "ambient_temperature",
    }
    report = rig.readiness_report()
    assert not report.computational_ready
    assert report.missing_required_measurements
