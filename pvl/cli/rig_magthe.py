from __future__ import annotations

import argparse
import json
from pathlib import Path

from pvl.experiments.models import CoilDriveState, DriveMode, ExperimentConfig
from pvl.geometry.constructive import compile_constructive_topology
from pvl.geometry.exploratory import architecture_example_rig_v1
from pvl.geometry.gmsh_rig import RigGmshConfig
from pvl.materials.library import load_builtin_material_library
from pvl.rig.fingerprint import rig_definition_fingerprint
from pvl.solvers.getdp.rig_magnetothermal_run import run_complete_rig_steady_magnetothermal
from pvl.solvers.getdp.runner import SolverExecutionError, SolverUnavailableError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pvl-rig-magthe")
    parser.add_argument("--output", default="results/rig_magthe_smoke")
    parser.add_argument("--frequency", type=float, default=10.0)
    parser.add_argument("--current", type=float, default=0.2)
    parser.add_argument("--ambient-k", type=float, default=293.15)
    parser.add_argument("--mesh-size", type=float, default=0.04)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.frequency <= 0.0 or args.current <= 0.0 or args.mesh_size <= 0.0 or args.ambient_k <= 0.0:
        raise SystemExit("frequency, current, ambient temperature and mesh size must be positive")

    rig = architecture_example_rig_v1()
    materials = load_builtin_material_library()
    topology = compile_constructive_topology(rig)
    experiment = ExperimentConfig(
        experiment_id="rig-magthe-smoke",
        repetitions=1,
        material_library_fingerprint=materials.fingerprint_sha256(),
        rig_definition_fingerprint=rig_definition_fingerprint(rig),
        coil_a=CoilDriveState(
            mode=DriveMode.HARMONIC,
            current_a=args.current,
            polarity=1,
            frequency_hz=args.frequency,
            phase_rad=0.0,
            omega_sign=1,
        ),
        coil_b=CoilDriveState(),
        notes="PVL-2V one-way ordinary magneto-quasistatic to steady thermal conduction smoke",
    )
    mesh_config = RigGmshConfig(
        characteristic_length_m=args.mesh_size,
        minimum_characteristic_length_m=0.001,
        air_margin_fraction=0.35,
        winding_characteristic_length_m=min(0.004, args.mesh_size),
        steel_characteristic_length_m=min(0.010, args.mesh_size),
    )
    try:
        result = run_complete_rig_steady_magnetothermal(
            experiment,
            topology,
            materials,
            mesh_config,
            Path(args.output),
            ambient_temperature_k=args.ambient_k,
            axis_samples=51,
            probe_y_m=(-0.03, 0.0, 0.03),
        )
    except SolverUnavailableError as exc:
        print(f"PVL complete-Rig magnetothermal status: NOT READY — {exc}")
        return 2
    except SolverExecutionError as exc:
        print(f"PVL complete-Rig magnetothermal status: SOLVER FAILED — {exc}")
        return 3

    payload = {
        "frequency_hz": result.mq_model.frequency_hz,
        "joule_input_w": result.joule_input_w,
        "metrics": result.metrics,
        "solver_versions": result.solver_versions,
        "solver_execution": True,
        "thermal_environment_model": "conduction_only_with_fixed_remote_air_boundary",
        "hypothesis_analysis": False,
        "physical_validation": False,
    }
    print(json.dumps(payload, indent=2))
    print("PVL-2V complete-Rig magneto-thermal conduction smoke: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
