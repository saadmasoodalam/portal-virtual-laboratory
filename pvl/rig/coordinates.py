from pvl.rig.measurements import LengthMeasurement


class CoordinateMeasurement(LengthMeasurement):
    """Position coordinate allowing zero and negative metre values."""

    value_m: float | None = None
