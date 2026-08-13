from pvl.rig.components import SensorDefinition, SensorKind
from pvl.rig.schema import RigV1Schema


def build_rig_v1_measurement_template() -> RigV1Schema:
    """Return a measurement template with physical dimensions intentionally unknown."""
    return RigV1Schema(
        sensors=[
            SensorDefinition(sensor_id="magnetic_primary", kind=SensorKind.MAGNETIC),
            SensorDefinition(sensor_id="temperature_sample", kind=SensorKind.TEMPERATURE),
            SensorDefinition(sensor_id="pickup_primary", kind=SensorKind.PICKUP),
            SensorDefinition(sensor_id="ambient_temperature", kind=SensorKind.AMBIENT),
        ]
    )
