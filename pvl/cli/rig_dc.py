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
from pvl.solvers.getdp.rig_magnetostatic_run import run_complete_rig_dc_magnetostatic
from pvl.solvers.getdp.runner import SolverUnavailableError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pvl-rig-dc")
    parser.add_argument("--output", default="results/rig_dc_smoke")
    parser.add_argument("--mesh-size", type=float, default=0.04)
    parser.add_argument("--minimum-mesh-size", type=float, default=0.001)
    parser.add_argument("--air-margin-fraction", type=float, default=0.35)
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
        experiment_id="rig-dc-smoke",
        repetitions=1,
        randomization_seed=0,
        material_library_fingerprint=materials.fingerprint_sha256(),
        rig_definition_fingerprint=rig_definition_fingerprint(rig),
        coil_a=CoilDriveState(mode=DriveMode.DC, current_a=args.current),
        coil_b=CoilDriveState(),
        notes="PVL-2Q exploratory single-coil complete-Rig DC solver smoke state",
    )
    mesh_config = RigGmshConfig(
        characteristic_length_m=args.mesh_size,
        minimum_characteristic_length_m=args.minimum_mesh_size,
        air_margin_fraction=args.air_margin_fraction,
    )
    try:
        result = run_complete_rig_dc_magnetostatic(
            experiment,
            topology,
            materials,
            mesh_config,
            Path(args.output),
        )
    except SolverUnavailableError as exc:
        print(f"PVL complete-Rig DC status: NOT READY — {exc}")
        return 2
    payload = {
        "solver_versions": result.solver_versions,
        "source_ampere_turns": result.source_ampere_turns,
        "nodes": result.mesh_run.summary.node_count,
        "tetrahedra": result.mesh_run.summary.tetrahedron_count,
        "outer_boundary_triangles": result.mesh_run.summary.triangles_by_physical_tag.get(
            result.mesh_run.gmsh_manifest.outer_boundary_physical_tag, 0
        ),
        "metrics": result.metrics,
        "solver_execution": True,
        "scope": "exploratory_unpersisted_solver_validation_primitive",
    }
    print(json.dumps(payload, indent=2))
    print("PVL-2Q complete-Rig DC magnetostatic smoke: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
