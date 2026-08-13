from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
from hashlib import sha256
import json
from typing import Literal

from pydantic import ConfigDict, Field, model_validator

from pvl.core.models import FrozenModel


class DriveMode(StrEnum):
    OFF = "off"
    DC = "dc"
    HARMONIC = "harmonic"


class SampleMedium(StrEnum):
    AIR = "air"
    DISTILLED_WATER = "distilled_water"
    SALINE_0P9 = "saline_0p9"


class BoundaryCircuitState(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class ExperimentPurpose(StrEnum):
    BASELINE = "baseline"
    CALIBRATION = "calibration"
    VALIDATION = "validation"
    SWEEP = "sweep"


class SolverFidelity(StrEnum):
    EXPLORATORY = "exploratory"
    HARDWARE_FIDELITY = "hardware_fidelity"


class RunStatus(StrEnum):
    PLANNED = "planned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class CoilDriveState(FrozenModel):
    mode: DriveMode = DriveMode.OFF
    current_a: float = Field(default=0.0, ge=0.0)
    polarity: Literal[-1, 1] = 1
    frequency_hz: float | None = Field(default=None, gt=0.0)
    phase_rad: float = 0.0
    omega_sign: Literal[-1, 1] = 1

    @model_validator(mode="after")
    def validate_drive(self) -> "CoilDriveState":
        if self.mode == DriveMode.OFF:
            if self.current_a != 0.0 or self.frequency_hz is not None or self.phase_rad != 0.0:
                raise ValueError("OFF drive requires zero current, no frequency, and zero phase")
        elif self.mode == DriveMode.DC:
            if self.current_a <= 0.0:
                raise ValueError("DC drive requires positive current magnitude")
            if self.frequency_hz is not None or self.phase_rad != 0.0:
                raise ValueError("DC drive must not define frequency or phase")
        else:
            if self.current_a <= 0.0 or self.frequency_hz is None:
                raise ValueError("harmonic drive requires positive current and frequency")
        return self

    @property
    def signed_current_a(self) -> float:
        return self.current_a * self.polarity

    @property
    def canonical_positive_frequency_phase_rad(self) -> float:
        return self.omega_sign * self.phase_rad


class EnvironmentSnapshot(FrozenModel):
    captured_utc: datetime
    temperature_k: float | None = Field(default=None, gt=0.0)
    relative_humidity_percent: float | None = Field(default=None, ge=0.0, le=100.0)
    pressure_pa: float | None = Field(default=None, gt=0.0)
    calibration_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def require_utc_timestamp(self) -> "EnvironmentSnapshot":
        if self.captured_utc.tzinfo is None or self.captured_utc.utcoffset() != timedelta(0):
            raise ValueError("captured_utc must be timezone-aware UTC")
        return self


class ExperimentConfig(FrozenModel):
    experiment_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    rig_id: str = "portal_boundary_physics_rig_v1"
    purpose: ExperimentPurpose = ExperimentPurpose.BASELINE
    medium: SampleMedium = SampleMedium.AIR
    copper_boundary_state: BoundaryCircuitState = BoundaryCircuitState.OPEN
    coil_a: CoilDriveState = CoilDriveState()
    coil_b: CoilDriveState = CoilDriveState()
    duration_s: float = Field(default=60.0, gt=0.0)
    repetitions: int = Field(default=3, ge=1)
    randomization_seed: int = Field(default=0, ge=0)
    solver_fidelity: SolverFidelity = SolverFidelity.EXPLORATORY
    material_library_fingerprint: str = Field(min_length=64, max_length=64)
    rig_definition_fingerprint: str = Field(min_length=64, max_length=64)
    biological_testing: Literal[False] = False
    notes: str = ""

    def physics_state_payload(self) -> dict[str, object]:
        return {
            "rig_id": self.rig_id,
            "medium": self.medium.value,
            "copper_boundary_state": self.copper_boundary_state.value,
            "coil_a": self.coil_a.model_dump(mode="json"),
            "coil_b": self.coil_b.model_dump(mode="json"),
            "duration_s": self.duration_s,
            "material_library_fingerprint": self.material_library_fingerprint,
            "rig_definition_fingerprint": self.rig_definition_fingerprint,
        }

    def physics_state_hash(self) -> str:
        payload = json.dumps(self.physics_state_payload(), sort_keys=True, separators=(",", ":"))
        return sha256(payload.encode("utf-8")).hexdigest()


class RunManifest(FrozenModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    experiment_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    repetition_index: int = Field(ge=1)
    randomized_sequence_index: int = Field(ge=0)
    planned_configuration_hash: str = Field(min_length=64, max_length=64)
    physics_state_hash: str = Field(min_length=64, max_length=64)
    rig_definition_fingerprint: str = Field(min_length=64, max_length=64)
    material_library_fingerprint: str = Field(min_length=64, max_length=64)
    created_utc: datetime
    status: RunStatus = RunStatus.PLANNED
    solver_versions: dict[str, str] = Field(default_factory=dict)
    paths: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_utc_timestamp(self) -> "RunManifest":
        if self.created_utc.tzinfo is None or self.created_utc.utcoffset() != timedelta(0):
            raise ValueError("created_utc must be timezone-aware UTC")
        return self
