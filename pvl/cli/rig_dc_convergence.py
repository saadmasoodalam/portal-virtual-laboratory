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
        # Run #150 showed that exact point probes removed the line-interpolation confound, but the
        # 75% -> 100% outer-domain comparison still moved materially while the direct solve became
        # very expensive. Keep the retained 20/15/12 mm near-Rig sequence plus 2 mm winding and
        # 5 mm steel refinement, while grading only distant air toward 40 mm. The fixed 25% near
        # box is identical across the 50/75/100% domain sequence, so enlargement changes the
        # truncation boundary without intentionally coarsening the Rig/probe region. The 3%
        # acceptance limits remain unchanged.
        mesh_points, domain_points, gate = run_rig_dc_mesh_and_domain_convergence(
            experiment,
            topology,
            materials,
            Path(args.output),
            mesh_sizes_m=(0.020, 0.015, 0.012),
            air_margins=(0.50, 0.75, 1.00),
            shared_mesh_size_m=0.012,
            shared_air_margin=0.75,
            winding_mesh_size_m=0.002,
            steel_mesh_size_m=0.005,
            far_field_mesh_size_m=0.040,
            far_field_near_margin_fraction=0.25,
            far_field_transition_m=0.10,
            probe_y_m=(-0.060, -0.030, 0.0, 0.030, 0.060),
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
