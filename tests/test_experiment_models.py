from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from pvl.experiments.models import (
    BoundaryCircuitState,
    CoilDriveState,
    DriveMode,
    EnvironmentSnapshot,
    ExperimentConfig,
    SampleMedium,
)


FINGERPRINT = "a" * 64
RIG_FINGERPRINT = "b" * 64


def _config(**updates):
    values = {
        "experiment_id": "rig-v1-baseline",
        "material_library_fingerprint": FINGERPRINT,
        "rig_definition_fingerprint": RIG_FINGERPRINT,
    }
    values.update(updates)
    return ExperimentConfig(**values)


def test_default_experiment_is_air_open_boundary_and_non_biological():
    config = _config()
    assert config.medium == SampleMedium.AIR
    assert config.medium.material_id == "air_baseline"
    assert config.copper_boundary_state == BoundaryCircuitState.OPEN
    assert config.biological_testing is False


def test_off_drive_rejects_hidden_state_parameters():
    with pytest.raises(ValidationError):
        CoilDriveState(mode=DriveMode.OFF, current_a=1.0)
    with pytest.raises(ValidationError):
        CoilDriveState(mode=DriveMode.OFF, phase_rad=0.5)
    with pytest.raises(ValidationError):
        CoilDriveState(mode=DriveMode.OFF, polarity=-1)


def test_dc_and_harmonic_drive_require_explicit_valid_parameters():
    with pytest.raises(ValidationError):
        CoilDriveState(mode=DriveMode.DC)
    with pytest.raises(ValidationError):
        CoilDriveState(mode=DriveMode.DC, current_a=1.0, omega_sign=-1)
    with pytest.raises(ValidationError):
        CoilDriveState(mode=DriveMode.HARMONIC, current_a=1.0)
    drive = CoilDriveState(
        mode=DriveMode.HARMONIC,
        current_a=1.0,
        frequency_hz=100.0,
        phase_rad=0.7,
        omega_sign=-1,
    )
    assert drive.canonical_positive_frequency_phase_rad == -0.7


def test_repetition_and_randomization_metadata_do_not_change_physics_hash():
    first = _config(repetitions=3, randomization_seed=10, notes="first")
    second = _config(repetitions=5, randomization_seed=99, notes="second")
    assert first.physics_state_hash() == second.physics_state_hash()
    assert first.configuration_hash() != second.configuration_hash()


def test_duration_and_medium_are_part_of_physics_hash():
    base = _config()
    assert base.physics_state_hash() != _config(duration_s=120.0).physics_state_hash()
    assert base.physics_state_hash() != _config(medium=SampleMedium.DISTILLED_WATER).physics_state_hash()


def test_environment_snapshot_requires_utc_timestamp():
    EnvironmentSnapshot(captured_utc=datetime.now(timezone.utc), temperature_k=293.15)
    with pytest.raises(ValidationError):
        EnvironmentSnapshot(captured_utc=datetime.now(), temperature_k=293.15)


def test_biological_testing_cannot_be_enabled():
    with pytest.raises(ValidationError):
        _config(biological_testing=True)
