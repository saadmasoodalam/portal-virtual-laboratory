from pvl.experiments.models import CoilDriveState, DriveMode, ExperimentConfig
from pvl.orchestrator.preflight import SolverRoute, _solver_route


def _base(a, b):
    return ExperimentConfig(
        experiment_id="unsupported",
        material_library_fingerprint="a" * 64,
        rig_definition_fingerprint="b" * 64,
        coil_a=a,
        coil_b=b,
    )


def test_mixed_dc_and_harmonic_drives_are_separate_runs():
    dc = CoilDriveState(mode=DriveMode.DC, current_a=1.0)
    ac = CoilDriveState(mode=DriveMode.HARMONIC, current_a=1.0, frequency_hz=100.0)
    route, issues = _solver_route(_base(dc, ac))
    assert route == SolverRoute.UNSUPPORTED
    assert issues[0].code == "mixed_drive_modes_not_supported"


def test_two_harmonic_frequencies_are_separate_runs():
    a = CoilDriveState(mode=DriveMode.HARMONIC, current_a=1.0, frequency_hz=100.0)
    b = CoilDriveState(mode=DriveMode.HARMONIC, current_a=1.0, frequency_hz=200.0)
    route, issues = _solver_route(_base(a, b))
    assert route == SolverRoute.UNSUPPORTED
    assert issues[0].code == "multifrequency_not_supported"
