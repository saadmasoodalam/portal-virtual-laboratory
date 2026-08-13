from pvl.experiments.models import CoilDriveState, DriveMode, ExperimentConfig
from pvl.orchestrator.preflight import SolverRoute, _solver_route


def test_dc_drive_routes_to_magnetostatic_solver():
    config = ExperimentConfig(
        experiment_id="dc-route",
        material_library_fingerprint="a" * 64,
        rig_definition_fingerprint="b" * 64,
        coil_a=CoilDriveState(mode=DriveMode.DC, current_a=1.0),
    )
    route, issues = _solver_route(config)
    assert route == SolverRoute.MAGNETOSTATIC
    assert not issues
