from pvl.experiments.models import CoilDriveState, DriveMode, ExperimentConfig
from pvl.orchestrator.preflight import SolverRoute, _solver_route


def test_common_frequency_harmonic_drives_route_to_mq_solver():
    drive = CoilDriveState(mode=DriveMode.HARMONIC, current_a=1.0, frequency_hz=100.0)
    config = ExperimentConfig(
        experiment_id="ac-route",
        material_library_fingerprint="a" * 64,
        rig_definition_fingerprint="b" * 64,
        coil_a=drive,
        coil_b=drive,
    )
    route, issues = _solver_route(config)
    assert route == SolverRoute.MAGNETOQUASISTATIC
    assert not issues
