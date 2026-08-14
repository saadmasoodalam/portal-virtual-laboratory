from __future__ import annotations

from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from itertools import product

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pvl.experiments.models import (
    BoundaryCircuitState,
    CoilDriveState,
    DriveMode,
    ExperimentConfig,
    SampleMedium,
)
from pvl.materials.library import MaterialLibrary
from pvl.orchestrator.preflight import preflight_experiment
from pvl.rig.fingerprint import rig_definition_fingerprint
from pvl.rig.schema import RigV1Schema


SWEEP_SCHEMA_VERSION = "pvl-dc-sweep-v1"


class NumericRange(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    start: float
    stop: float
    step: float = Field(gt=0.0)

    @model_validator(mode="after")
    def direction(self) -> "NumericRange":
        if self.start > self.stop:
            raise ValueError("numeric sweep range requires start <= stop")
        return self

    def values(self) -> tuple[float, ...]:
        """Generate an inclusive decimal grid without binary floating-point drift."""
        try:
            start = Decimal(str(self.start))
            stop = Decimal(str(self.stop))
            step = Decimal(str(self.step))
        except InvalidOperation as exc:
            raise ValueError("numeric sweep range contains an invalid decimal value") from exc
        count = int((stop - start) // step)
        values = [start + step * index for index in range(count + 1)]
        if not values or values[-1] != stop:
            values.append(stop)
        return tuple(float(value) for value in values)


class DcSweepDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    sweep_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    coil_a_current_a: NumericRange
    coil_b_current_a: NumericRange
    media: tuple[SampleMedium, ...] = (SampleMedium.AIR,)
    copper_boundary_states: tuple[BoundaryCircuitState, ...] = (BoundaryCircuitState.OPEN,)
    maximum_points: int = Field(default=10_000, gt=0, le=100_000)

    @model_validator(mode="after")
    def nonempty_axes(self) -> "DcSweepDefinition":
        if not self.media:
            raise ValueError("DC sweep requires at least one medium")
        if not self.copper_boundary_states:
            raise ValueError("DC sweep requires at least one copper boundary state")
        if len(set(self.media)) != len(self.media):
            raise ValueError("DC sweep media must be unique")
        if len(set(self.copper_boundary_states)) != len(self.copper_boundary_states):
            raise ValueError("DC sweep copper boundary states must be unique")
        return self


class DcSweepPoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    index: int = Field(ge=0)
    point_id: str
    point_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    signed_coil_a_current_a: float
    signed_coil_b_current_a: float
    medium: SampleMedium
    copper_boundary_state: BoundaryCircuitState
    rig_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    configuration_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    physics_state_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    rig: RigV1Schema
    experiment: ExperimentConfig


class DcSweepPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: str = SWEEP_SCHEMA_VERSION
    sweep_id: str
    sweep_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    point_count: int = Field(gt=0)
    points: tuple[DcSweepPoint, ...]
    solver_execution: bool = False
    hypothesis_analysis: bool = False

    @model_validator(mode="after")
    def count_matches(self) -> "DcSweepPlan":
        if self.point_count != len(self.points):
            raise ValueError("DC sweep point count does not match point records")
        if tuple(point.index for point in self.points) != tuple(range(self.point_count)):
            raise ValueError("DC sweep point indices must be contiguous and deterministic")
        return self


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return sha256(encoded).hexdigest()


def _drive(signed_current_a: float) -> CoilDriveState:
    if signed_current_a == 0.0:
        return CoilDriveState()
    return CoilDriveState(
        mode=DriveMode.DC,
        current_a=abs(signed_current_a),
        polarity=1 if signed_current_a > 0.0 else -1,
    )


def _rig_for_state(
    base_rig: RigV1Schema,
    medium: SampleMedium,
    copper_state: BoundaryCircuitState,
) -> RigV1Schema:
    rig = base_rig.model_copy(deep=True)
    rig.sample_chamber.medium_material_id = medium.material_id
    rig.copper_boundary.baseline_open_loop = copper_state == BoundaryCircuitState.OPEN
    return rig


def plan_dc_sweep(
    definition: DcSweepDefinition,
    *,
    base_rig: RigV1Schema,
    base_experiment: ExperimentConfig,
    materials: MaterialLibrary,
) -> DcSweepPlan:
    """Create a deterministic Cartesian sweep whose labels match each constructive Rig state."""
    a_values = definition.coil_a_current_a.values()
    b_values = definition.coil_b_current_a.values()
    cardinality = (
        len(a_values)
        * len(b_values)
        * len(definition.media)
        * len(definition.copper_boundary_states)
    )
    if cardinality > definition.maximum_points:
        raise ValueError(
            f"DC sweep expands to {cardinality} points, exceeding maximum_points={definition.maximum_points}"
        )
    if base_experiment.material_library_fingerprint != materials.fingerprint_sha256():
        raise ValueError("base experiment material fingerprint does not match loaded library")

    points: list[DcSweepPoint] = []
    for index, (a_current, b_current, medium, copper_state) in enumerate(
        product(a_values, b_values, definition.media, definition.copper_boundary_states)
    ):
        rig = _rig_for_state(base_rig, medium, copper_state)
        rig_fingerprint = rig_definition_fingerprint(rig)
        experiment = base_experiment.model_copy(
            update={
                "experiment_id": f"{definition.sweep_id}-p{index:06d}",
                "medium": medium,
                "copper_boundary_state": copper_state,
                "coil_a": _drive(a_current),
                "coil_b": _drive(b_current),
                "rig_definition_fingerprint": rig_fingerprint,
            }
        )
        report = preflight_experiment(experiment, rig, materials)
        if not report.ready:
            codes = ",".join(issue.code for issue in report.issues)
            raise ValueError(f"generated DC sweep point {index} failed preflight: {codes}")
        payload = {
            "schema_version": SWEEP_SCHEMA_VERSION,
            "sweep_id": definition.sweep_id,
            "index": index,
            "signed_coil_a_current_a": a_current,
            "signed_coil_b_current_a": b_current,
            "medium": medium.value,
            "copper_boundary_state": copper_state.value,
            "rig_fingerprint": rig_fingerprint,
            "configuration_hash": experiment.configuration_hash(),
            "physics_state_hash": experiment.physics_state_hash(),
        }
        point_hash = _canonical_hash(payload)
        points.append(
            DcSweepPoint(
                index=index,
                point_id=f"{definition.sweep_id}-p{index:06d}",
                point_hash=point_hash,
                signed_coil_a_current_a=a_current,
                signed_coil_b_current_a=b_current,
                medium=medium,
                copper_boundary_state=copper_state,
                rig_fingerprint=rig_fingerprint,
                configuration_hash=experiment.configuration_hash(),
                physics_state_hash=experiment.physics_state_hash(),
                rig=rig,
                experiment=experiment,
            )
        )

    sweep_hash = _canonical_hash(
        {
            "schema_version": SWEEP_SCHEMA_VERSION,
            "definition": definition.model_dump(mode="json"),
            "base_experiment_configuration_hash": base_experiment.configuration_hash(),
            "material_library_fingerprint": materials.fingerprint_sha256(),
            "point_hashes": [point.point_hash for point in points],
        }
    )
    return DcSweepPlan(
        sweep_id=definition.sweep_id,
        sweep_hash=sweep_hash,
        point_count=len(points),
        points=tuple(points),
    )
