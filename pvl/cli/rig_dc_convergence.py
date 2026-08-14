from __future__ import annotations

import argparse
import json
from pathlib import Path

from pvl.experiments.models import CoilDriveState, DriveMode, ExperimentConfig
from pvl.geometry.constructive import compile_constructive_topology
from pvl.geometry.exploratory import architecture_example_rig_v1
from pvl.materials.library import load_builtin_material_library
from pvl.rig.fingerprint import rig_definition_fingerprint
from pvl.solvers.getdp.runner import SolverUnavailableError
from pvl.validation.rig_magnetostatic import run_rig_dc_mesh_and_domain_convergence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pvl-rig-dc-convergence")
    parser.add_argument("--output", default="results/rig_dc_convergence")
    parser.add_argument("--current", type=float, default=1.0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.current <= 0.0:
        raise SystemExit("--current must be positive")

    rig = architecture_example_rig_v1()
    materials = load_builtin_material_library()
    topology = compile_constructive_topology(rig)
    experiment = ExperimentConfig(
        experiment_id="rig-dc-convergence",
        repetitions=1,
        randomization_seed=0,
        material_library_fingerprint=materials.fingerprint_sha256(),
        rig_definition_fingerprint=rig_definition_fingerprint(rig),
        coil_a=CoilDriveState(mode=DriveMode.DC, current_a=args.current),
        coil_b=CoilDriveState(),
        notes="PVL-2Q exploratory complete-Rig numerical convergence state",
    )
    try:
        # Run #163 established that finite-aperture averaging removes much of the first-order
        # H(curl) element-membership noise, but 15 -> 12 mm remained outside the retained 3% gate
        # (5.46% probe, 6.78% center) and the 75% -> 100% air-domain probe comparison remained
        # 12.33%. That means the old sequence was still pre-asymptotic; the correct response is a
        # finer mesh and a farther truncation boundary, not a weaker tolerance. Distant air remains
        # graded to 40 mm and the winding/steel local targets stay fixed so the extra cost is spent
        # where the field observable is sensitive.
        mesh_points, domain_points, gate = run_rig_dc_mesh_and_domain_convergence(
            experiment,
            topology,
            materials,
            Path(args.output),
            mesh_sizes_m=(0.012, 0.010, 0.008),
            air_margins=(1.00, 1.25, 1.50),
            shared_mesh_size_m=0.008,
            shared_air_margin=1.25,
            winding_mesh_size_m=0.002,
            steel_mesh_size_m=0.005,
            far_field_mesh_size_m=0.040,
            far_field_near_margin_fraction=0.25,
            far_field_transition_m=0.10,
            probe_y_m=(-0.060, -0.030, 0.0, 0.030, 0.060),
            probe_window_half_width_m=0.005,
            probe_window_samples=21,
        )
    except SolverUnavailableError as exc:
        print(f"PVL complete-Rig DC convergence status: NOT READY — {exc}")
        return 2

    payload = {
        "mesh_sequence": [point.__dict__ for point in mesh_points],
        "domain_sequence": [point.__dict__ for point in domain_points],
        "validation_gate": gate.as_dict(),
        "solver_execution": True,
        "scope": "exploratory_numerical_convergence_validation",
    }
    print(json.dumps(payload, indent=2))
    if not gate.passed:
        print("PVL-2Q complete-Rig DC convergence gate: FAILED")
        return 9
    print("PVL-2Q complete-Rig DC convergence gate: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
