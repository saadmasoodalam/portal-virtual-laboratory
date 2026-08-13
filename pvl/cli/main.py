from __future__ import annotations

import argparse
import json
from pathlib import Path

from pvl.core.models import POC001Config
from pvl.geometry.poc001 import write_gmsh_geo
from pvl.solvers.getdp.runner import SolverUnavailableError, discover_executables
from pvl.validation.poc001 import analytical_reference


def _cmd_poc001(args: argparse.Namespace) -> int:
    config = POC001Config()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    geo_path = write_gmsh_geo(config, out / "poc001.geo")
    reference = analytical_reference(config)
    payload = {
        "experiment": config.model_dump(mode="json"),
        "configuration_hash": config.configuration_hash(),
        "analytical_reference": [
            {"z_m": float(z), "b_t": float(b)} for z, b in zip(reference.z_m, reference.b_t)
        ],
        "geometry_file": str(geo_path),
    }
    (out / "reference.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


def _cmd_doctor(_: argparse.Namespace) -> int:
    try:
        executables = discover_executables()
    except SolverUnavailableError as exc:
        print(f"PVL FEM status: NOT READY — {exc}")
        return 2
    print(f"PVL FEM status: READY — gmsh={executables.gmsh}, getdp={executables.getdp}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pvl")
    sub = parser.add_subparsers(dest="command", required=True)
    poc = sub.add_parser("poc001", help="generate POC-001 geometry and analytical reference")
    poc.add_argument("--output", default="results/poc001")
    poc.set_defaults(func=_cmd_poc001)
    doctor = sub.add_parser("doctor", help="check external FEM executables")
    doctor.set_defaults(func=_cmd_doctor)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
