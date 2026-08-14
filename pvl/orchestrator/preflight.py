from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from pvl.experiments.models import (
    BoundaryCircuitState,
    DriveMode,
    ExperimentConfig,
    SolverFidelity,
)
from pvl.materials.library import MaterialLibrary
from pvl.rig.fingerprint import rig_definition_fingerprint
from pvl.rig.material_check import check_material_references
from pvl.rig.schema import RigV1Schema


class SolverRoute(StrEnum):
    CONTROL = "control"
    MAGNETOSTATIC = "magnetostatic"
    MAGNETOQUASISTATIC = "magnetoquasistatic"
    UNSUPPORTED = "unsupported"


class IssueSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class PreflightIssue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    code: str
    severity: IssueSeverity
    message: str


class PreflightReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    ready: bool
    solver_route: SolverRoute
    issues: tuple[PreflightIssue, ...]
    actual_rig_fingerprint: str
    actual_material_fingerprint: str


def _solver_route(config: ExperimentConfig) -> tuple[SolverRoute, list[PreflightIssue]]:
    active = [drive for drive in (config.coil_a, config.coil_b) if drive.mode != DriveMode.OFF]
    if not active:
        return SolverRoute.CONTROL, []

    modes = {drive.mode for drive in active}
    if modes == {DriveMode.DC}:
        return SolverRoute.MAGNETOSTATIC, []
    if modes == {DriveMode.HARMONIC}:
        frequencies = {drive.frequency_hz for drive in active}
        if len(frequencies) == 1:
            return SolverRoute.MAGNETOQUASISTATIC, []
        return SolverRoute.UNSUPPORTED, [
            PreflightIssue(
                code="multifrequency_not_supported",
                severity=IssueSeverity.ERROR,
                message="one frequency-domain solve requires a common active-coil frequency",
            )
        ]
    return SolverRoute.UNSUPPORTED, [
        PreflightIssue(
            code="mixed_drive_modes_not_supported",
            severity=IssueSeverity.ERROR,
            message="DC and harmonic active coils require separate solver runs",
        )
    ]


def _state_geometry_consistency(config: ExperimentConfig, rig: RigV1Schema) -> list[PreflightIssue]:
    """Reject experiment states that do not match the constructive Rig snapshot.

    The complete-Rig solver compiles the sample material and copper gap directly from ``rig``. An
    ExperimentConfig is therefore not allowed to claim a different medium or open/closed boundary
    while retaining the same Rig fingerprint. Silent disagreement would label one physical mesh as
    a different experiment state and corrupt comparisons.
    """
    issues: list[PreflightIssue] = []
    if config.medium.material_id != rig.sample_chamber.medium_material_id:
        issues.append(
            PreflightIssue(
                code="sample_medium_geometry_mismatch",
                severity=IssueSeverity.ERROR,
                message=(
                    "experiment sample medium does not match the material compiled into the Rig "
                    "geometry; create/update the Rig state before solving this medium"
                ),
            )
        )
    rig_boundary_state = (
        BoundaryCircuitState.OPEN
        if rig.copper_boundary.baseline_open_loop
        else BoundaryCircuitState.CLOSED
    )
    if config.copper_boundary_state != rig_boundary_state:
        issues.append(
            PreflightIssue(
                code="copper_boundary_geometry_mismatch",
                severity=IssueSeverity.ERROR,
                message=(
                    "experiment copper boundary state does not match the open/closed topology "
                    "compiled from the Rig definition"
                ),
            )
        )
    return issues


def preflight_experiment(
    config: ExperimentConfig,
    rig: RigV1Schema,
    materials: MaterialLibrary,
) -> PreflightReport:
    issues: list[PreflightIssue] = []
    actual_rig = rig_definition_fingerprint(rig)
    actual_materials = materials.fingerprint_sha256()

    if config.rig_definition_fingerprint != actual_rig:
        issues.append(PreflightIssue(
            code="rig_fingerprint_mismatch",
            severity=IssueSeverity.ERROR,
            message="experiment was not planned against this Rig definition",
        ))
    if config.material_library_fingerprint != actual_materials:
        issues.append(PreflightIssue(
            code="material_fingerprint_mismatch",
            severity=IssueSeverity.ERROR,
            message="experiment was not planned against this material library",
        ))

    readiness = rig.readiness_report()
    if not readiness.computational_ready:
        issues.append(PreflightIssue(
            code="rig_measurements_incomplete",
            severity=IssueSeverity.ERROR,
            message="required Rig measurements are still unknown",
        ))
    elif config.solver_fidelity == SolverFidelity.HARDWARE_FIDELITY and not readiness.hardware_fidelity_ready:
        issues.append(PreflightIssue(
            code="rig_measurements_not_hardware_fidelity",
            severity=IssueSeverity.ERROR,
            message="hardware-fidelity mode requires measured or supplier-sourced Rig dimensions",
        ))

    material_report = check_material_references(rig, materials)
    if not material_report.references_valid:
        issues.append(PreflightIssue(
            code="missing_rig_material",
            severity=IssueSeverity.ERROR,
            message="one or more Rig material identifiers are missing from the selected library",
        ))

    medium = materials.get(config.medium.material_id)
    if medium is None:
        issues.append(PreflightIssue(
            code="missing_sample_medium",
            severity=IssueSeverity.ERROR,
            message="selected sample medium is missing from the material library",
        ))

    issues.extend(_state_geometry_consistency(config, rig))

    if config.solver_fidelity == SolverFidelity.HARDWARE_FIDELITY:
        if not material_report.hardware_fidelity_ready or (medium is not None and not medium.is_hardware_fidelity_data):
            issues.append(PreflightIssue(
                code="materials_not_hardware_fidelity",
                severity=IssueSeverity.ERROR,
                message="hardware-fidelity mode requires measured or supplier-sourced material data",
            ))

    route, route_issues = _solver_route(config)
    issues.extend(route_issues)
    ready = not any(issue.severity == IssueSeverity.ERROR for issue in issues)
    return PreflightReport(
        ready=ready,
        solver_route=route,
        issues=tuple(issues),
        actual_rig_fingerprint=actual_rig,
        actual_material_fingerprint=actual_materials,
    )
