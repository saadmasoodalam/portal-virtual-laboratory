from __future__ import annotations

from collections import defaultdict
from math import isfinite
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator


COMPARISON_SCHEMA_VERSION = "pvl-physics-comparison-v1"


class PhysicsSample(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    run_id: str
    state_id: str
    repetition_index: int = Field(ge=0)
    parameter_value: float
    metrics: dict[str, float]
    mesh_configuration_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    configuration_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    solver_execution: bool = True
    checksum_verified: bool = True
    physical_validation: bool = False
    hypothesis_analysis: bool = False

    @model_validator(mode="after")
    def finite_values(self) -> "PhysicsSample":
        if not isfinite(self.parameter_value):
            raise ValueError("comparison parameter value must be finite")
        if not self.metrics:
            raise ValueError("physics comparison sample requires metrics")
        if not all(isinstance(name, str) and name and isfinite(float(value)) for name, value in self.metrics.items()):
            raise ValueError("physics comparison metrics must have finite numeric values")
        if not self.checksum_verified:
            raise ValueError("unverified scientific result cannot enter physics comparison")
        if self.hypothesis_analysis:
            raise ValueError("physics comparison cannot consume a hypothesis-mutated sample")
        return self


class PhysicsComparisonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    comparison_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    parameter_name: str
    metric_name: str
    samples: tuple[PhysicsSample, ...]
    control_state_id: str | None = None
    temperature_metric_name: str | None = None
    minimum_repetitions: int = Field(default=3, ge=2)
    max_relative_std: float = Field(default=0.05, gt=0.0)
    transition_robust_z: float = Field(default=5.0, gt=0.0)
    thermal_abs_correlation_threshold: float = Field(default=0.90, gt=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_samples(self) -> "PhysicsComparisonRequest":
        if not self.samples:
            raise ValueError("physics comparison requires samples")
        missing = [sample.run_id for sample in self.samples if self.metric_name not in sample.metrics]
        if missing:
            raise ValueError(f"comparison metric missing from sample(s): {', '.join(missing[:5])}")
        if self.temperature_metric_name is not None:
            missing_temp = [
                sample.run_id
                for sample in self.samples
                if self.temperature_metric_name not in sample.metrics
            ]
            if missing_temp:
                raise ValueError(
                    f"temperature control metric missing from sample(s): {', '.join(missing_temp[:5])}"
                )
        return self


class StateSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    state_id: str
    parameter_value: float
    repetition_count: int
    mean: float
    sample_std: float
    relative_std: float
    standard_error: float
    repeatability_passed: bool
    mesh_hash_count: int
    mesh_identity_consistent: bool
    control_subtracted_mean: float | None = None


class AdjacentDifference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    left_state_id: str
    right_state_id: str
    left_parameter: float
    right_parameter: float
    delta_parameter: float
    delta_metric: float
    derivative: float
    robust_z: float
    transition_candidate: bool


class PhysicsComparisonResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["pvl-physics-comparison-v1"] = COMPARISON_SCHEMA_VERSION
    comparison_id: str
    parameter_name: str
    metric_name: str
    state_summaries: tuple[StateSummary, ...]
    adjacent_differences: tuple[AdjacentDifference, ...]
    control_state_id: str | None
    control_mean: float | None
    repeatability_gate_passed: bool
    mesh_identity_gate_passed: bool
    all_samples_solver_executed: bool
    all_samples_checksum_verified: bool
    any_sample_physically_validated: bool
    thermal_correlation: float | None
    thermal_tracking_flag: bool
    transition_candidate_count: int
    unexplained_residual_claim_allowed: Literal[False] = False
    portal_interpretation_allowed: Literal[False] = False
    next_action: str


def _sample_std(values: np.ndarray) -> float:
    return float(np.std(values, ddof=1)) if values.size > 1 else 0.0


def _relative_std(values: np.ndarray, mean: float, global_scale: float) -> float:
    std = _sample_std(values)
    scale = max(abs(mean), global_scale, np.finfo(float).tiny)
    return float(std / scale)


def _pearson(x: np.ndarray, y: np.ndarray) -> float | None:
    if x.size < 3 or y.size != x.size:
        return None
    if float(np.std(x)) <= np.finfo(float).tiny or float(np.std(y)) <= np.finfo(float).tiny:
        return None
    value = float(np.corrcoef(x, y)[0, 1])
    return value if isfinite(value) else None


def _robust_scores(values: np.ndarray) -> np.ndarray:
    """Return robust z-like scores using MAD, with a non-robust fallback for zero MAD."""
    if values.size == 0:
        return np.asarray([], dtype=float)
    median = float(np.median(values))
    absolute = np.abs(values - median)
    mad = float(np.median(absolute))
    if mad > np.finfo(float).tiny:
        return 0.6744897501960817 * (values - median) / mad
    std = float(np.std(values, ddof=1)) if values.size > 1 else 0.0
    if std > np.finfo(float).tiny:
        return (values - float(np.mean(values))) / std
    return np.zeros_like(values, dtype=float)


def compare_physics_series(request: PhysicsComparisonRequest) -> PhysicsComparisonResult:
    """Compare trusted solver evidence without performing project-specific interpretation.

    Samples are grouped by `(state_id, parameter_value)`. Repetition statistics are calculated
    first. Adjacent finite differences are only marked as transition candidates when both adjacent
    states pass repeatability and use one consistent mesh identity. A candidate is therefore a
    *physics investigation target*, not an anomaly or Portal classification.
    """
    grouped: dict[tuple[str, float], list[PhysicsSample]] = defaultdict(list)
    for sample in request.samples:
        grouped[(sample.state_id, sample.parameter_value)].append(sample)

    metric_all = np.asarray(
        [float(sample.metrics[request.metric_name]) for sample in request.samples], dtype=float
    )
    global_scale = max(float(np.max(np.abs(metric_all))), np.finfo(float).tiny)

    control_values = np.asarray(
        [
            float(sample.metrics[request.metric_name])
            for sample in request.samples
            if request.control_state_id is not None and sample.state_id == request.control_state_id
        ],
        dtype=float,
    )
    control_mean = float(np.mean(control_values)) if control_values.size else None
    if request.control_state_id is not None and control_mean is None:
        raise ValueError("requested control_state_id has no samples")

    summaries: list[StateSummary] = []
    for (state_id, parameter_value), samples in grouped.items():
        values = np.asarray([float(sample.metrics[request.metric_name]) for sample in samples], dtype=float)
        mean = float(np.mean(values))
        std = _sample_std(values)
        relative_std = _relative_std(values, mean, global_scale)
        hashes = {sample.mesh_configuration_hash for sample in samples}
        summaries.append(
            StateSummary(
                state_id=state_id,
                parameter_value=parameter_value,
                repetition_count=len(samples),
                mean=mean,
                sample_std=std,
                relative_std=relative_std,
                standard_error=float(std / np.sqrt(values.size)) if values.size else float("nan"),
                repeatability_passed=(
                    len(samples) >= request.minimum_repetitions
                    and relative_std <= request.max_relative_std
                ),
                mesh_hash_count=len(hashes),
                mesh_identity_consistent=len(hashes) == 1,
                control_subtracted_mean=(mean - control_mean) if control_mean is not None else None,
            )
        )
    summaries.sort(key=lambda item: (item.parameter_value, item.state_id))

    # Derivatives are meaningful only within one state family. Multiple state IDs can share an x
    # coordinate (e.g. different media); compare adjacent values independently within each family.
    summaries_by_state: dict[str, list[StateSummary]] = defaultdict(list)
    for summary in summaries:
        summaries_by_state[summary.state_id].append(summary)

    raw_adjacent: list[tuple[StateSummary, StateSummary, float, float, float]] = []
    for state_id in sorted(summaries_by_state):
        ordered = sorted(summaries_by_state[state_id], key=lambda item: item.parameter_value)
        for left, right in zip(ordered, ordered[1:]):
            dx = right.parameter_value - left.parameter_value
            if dx <= 0.0:
                raise ValueError(f"state family {state_id} has duplicate/non-increasing parameter values")
            dy = right.mean - left.mean
            raw_adjacent.append((left, right, dx, dy, dy / dx))

    derivative_values = np.asarray([item[4] for item in raw_adjacent], dtype=float)
    robust_scores = _robust_scores(derivative_values)
    differences: list[AdjacentDifference] = []
    for index, (left, right, dx, dy, derivative) in enumerate(raw_adjacent):
        score = float(robust_scores[index])
        gates = (
            left.repeatability_passed
            and right.repeatability_passed
            and left.mesh_identity_consistent
            and right.mesh_identity_consistent
        )
        differences.append(
            AdjacentDifference(
                left_state_id=left.state_id,
                right_state_id=right.state_id,
                left_parameter=left.parameter_value,
                right_parameter=right.parameter_value,
                delta_parameter=dx,
                delta_metric=dy,
                derivative=derivative,
                robust_z=score,
                transition_candidate=gates and abs(score) >= request.transition_robust_z,
            )
        )

    thermal_correlation = None
    if request.temperature_metric_name is not None:
        temperature = np.asarray(
            [float(sample.metrics[request.temperature_metric_name]) for sample in request.samples],
            dtype=float,
        )
        thermal_correlation = _pearson(metric_all, temperature)
    thermal_tracking = (
        thermal_correlation is not None
        and abs(thermal_correlation) >= request.thermal_abs_correlation_threshold
    )

    repeatability_gate = all(summary.repeatability_passed for summary in summaries)
    mesh_gate = all(summary.mesh_identity_consistent for summary in summaries)
    transition_count = sum(item.transition_candidate for item in differences)
    if not repeatability_gate:
        next_action = "repeat measurements/simulations; one or more states fail the repeatability gate"
    elif not mesh_gate:
        next_action = "resolve mesh-identity inconsistency before interpreting state differences"
    elif thermal_tracking:
        next_action = "treat the observed metric as thermally correlated until an independent control rejects that explanation"
    elif transition_count:
        next_action = "investigate transition candidate(s) with mesh/tolerance/material/control studies; no anomaly claim is authorized"
    else:
        next_action = "no abrupt transition survived the current physics-first comparison gate"

    return PhysicsComparisonResult(
        comparison_id=request.comparison_id,
        parameter_name=request.parameter_name,
        metric_name=request.metric_name,
        state_summaries=tuple(summaries),
        adjacent_differences=tuple(differences),
        control_state_id=request.control_state_id,
        control_mean=control_mean,
        repeatability_gate_passed=repeatability_gate,
        mesh_identity_gate_passed=mesh_gate,
        all_samples_solver_executed=all(sample.solver_execution for sample in request.samples),
        all_samples_checksum_verified=all(sample.checksum_verified for sample in request.samples),
        any_sample_physically_validated=any(sample.physical_validation for sample in request.samples),
        thermal_correlation=thermal_correlation,
        thermal_tracking_flag=thermal_tracking,
        transition_candidate_count=transition_count,
        next_action=next_action,
    )
