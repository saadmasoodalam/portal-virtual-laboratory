from __future__ import annotations

import argparse
import json
from pathlib import Path

from pvl.geometry.constructive import compile_constructive_topology
from pvl.geometry.exploratory import architecture_example_rig_v1
from pvl.geometry.gmsh_rig import RigGmshConfig
from pvl.geometry.gmsh_rig_run import GmshUnavailableError, run_complete_rig_mesh


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pvl-rig-mesh")
    parser.add_argument("--output", default="results/rig_mesh_smoke")
    parser.add_argument("--mesh-size", type=float, default=0.035)
    parser.add_argument("--minimum-mesh-size", type=float, default=0.001)
    parser.add_argument("--air-margin-fraction", type=float, default=0.35)
    parser.add_argument("--air-min-margin", type=float, default=0.05)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    rig = architecture_example_rig_v1()
    topology = compile_constructive_topology(rig)
    config = RigGmshConfig(
        characteristic_length_m=args.mesh_size,
        minimum_characteristic_length_m=args.minimum_mesh_size,
        air_margin_fraction=args.air_margin_fraction,
        air_min_margin_m=args.air_min_margin,
    )
    try:
        result = run_complete_rig_mesh(topology, config, Path(args.output))
    except GmshUnavailableError as exc:
        print(f"PVL complete-Rig mesh status: NOT READY — {exc}")
        return 2

    payload = {
        "gmsh_version": result.gmsh_version,
        "source_rig_fingerprint": result.gmsh_manifest.source_rig_fingerprint,
        "constructive_topology_fingerprint": result.gmsh_manifest.constructive_topology_fingerprint,
        "gmsh_configuration_hash": result.gmsh_manifest.gmsh_configuration_hash,
        "physical_volume_count": len(result.gmsh_manifest.required_physical_names),
        "nodes": result.summary.node_count,
        "tetrahedra": result.summary.tetrahedron_count,
        "minimum_tetra_volume_m3": result.summary.minimum_tetra_volume_m3,
        "minimum_mean_ratio_quality": result.summary.minimum_mean_ratio_quality,
        "mean_mean_ratio_quality": result.summary.mean_mean_ratio_quality,
        "validation_gate": result.gate.model_dump(mode="json"),
        "solver_execution": False,
    }
    print(json.dumps(payload, indent=2))
    if not result.gate.passed:
        print("PVL-2P complete-Rig exploratory mesh gate: FAILED")
        return 8
    print("PVL-2P complete-Rig exploratory mesh gate: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
