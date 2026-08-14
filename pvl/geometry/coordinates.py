from __future__ import annotations

from pydantic import BaseModel, ConfigDict


RIG_COORDINATE_CONVENTION_ID = "pvl-rig-v1-top-view-xyz-v1"


class RigCoordinateConvention(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    convention_id: str
    handedness: str
    units: str
    x_axis: str
    y_axis: str
    z_axis: str
    origin: str


RIG_V1_COORDINATE_CONVENTION = RigCoordinateConvention(
    convention_id=RIG_COORDINATE_CONVENTION_ID,
    handedness="right_handed",
    units="metres",
    x_axis="top-view west-to-east horizontal axis",
    y_axis="top-view south-to-north axis through Coil A, chamber and Coil B",
    z_axis="normal to the nonconductive base plane; positive upward",
    origin="nominal Rig geometric center at the sample-chamber centerline",
)
