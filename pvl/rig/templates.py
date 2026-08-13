from pvl.rig.components import SensorDefinition, SensorKind
from pvl.rig.models import RigV1Definition


def build_rig_v1_measurement_template() -> RigV1Definition:
    """Return the Rig v1 template with identities fixed and dimensions intentionally unknown."""
    return RigV1Definition(
        sensors=[
            SensorDefinition(sensor_id="magnetic_primary", kind=SensorKind.MAGNETIC),
            SensorDefinition(sensor_id="temperature_sample", kind=SensorKind.TEMPERATURE),
            SensorDefinition(sensor_id="pickup_primary", kind=SensorKind.PICKUP),
            SensorDefinition(sensor_id="ambient_temperature", kind=SensorKind.AMBIENT),
        ]
    )
