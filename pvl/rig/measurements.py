from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MeasurementStatus(StrEnum):
    UNKNOWN = "unknown"
    ILLUSTRATIVE = "illustrative"
    MEASURED = "measured"
    SUPPLIER = "supplier"


class LengthMeasurement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value_m: float | None = Field(default=None, gt=0.0)
    status: MeasurementStatus = MeasurementStatus.UNKNOWN
    source_note: str = ""
    required_for_solver: bool = True

    @model_validator(mode="after")
    def validate_status(self) -> "LengthMeasurement":
        if self.status == MeasurementStatus.UNKNOWN and self.value_m is not None:
            raise ValueError("unknown measurement must not contain a value")
        if self.status != MeasurementStatus.UNKNOWN and self.value_m is None:
            raise ValueError("non-unknown measurement status requires a value")
        return self

    @property
    def has_value(self) -> bool:
        return self.value_m is not None

    @property
    def is_hardware_fidelity(self) -> bool:
        return self.status in {MeasurementStatus.MEASURED, MeasurementStatus.SUPPLIER}


class CountMeasurement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: int | None = Field(default=None, gt=0)
    status: MeasurementStatus = MeasurementStatus.UNKNOWN
    source_note: str = ""
    required_for_solver: bool = True

    @model_validator(mode="after")
    def validate_status(self) -> "CountMeasurement":
        if self.status == MeasurementStatus.UNKNOWN and self.value is not None:
            raise ValueError("unknown count must not contain a value")
        if self.status != MeasurementStatus.UNKNOWN and self.value is None:
            raise ValueError("non-unknown count status requires a value")
        return self

    @property
    def has_value(self) -> bool:
        return self.value is not None

    @property
    def is_hardware_fidelity(self) -> bool:
        return self.status in {MeasurementStatus.MEASURED, MeasurementStatus.SUPPLIER}
