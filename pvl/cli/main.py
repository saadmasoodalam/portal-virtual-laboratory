from __future__ import annotations

import argparse
import json
from pathlib import Path

from pvl.core.models import MeshConfig, POC001Config, POC002Config, POC003Config
from pvl.geometry.poc001 import write_gmsh_geo
from pvl.solvers.getdp.poc001_run import evaluate_poc001_gate, run_mesh_convergence
from pvl.solvers.getdp.poc002_run import evaluate_poc002_gate, run_dual_mesh_convergence
from pvl.solvers.getdp.runner import SolverUnavailableError, discover_executables, solver_versions
from pvl.validation.poc001 import analytical_reference
from pvl.validation.poc003 import dual_coil_phasor_reference, evaluate_poc003_gate


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


def _cmd_poc001_fem(args: argparse.Namespace) -> int:
    try:
        executables = discover_executables()
    except SolverUnavailableError as exc:
        print(f"PVL FEM status: NOT READY — {exc}")
        return 2

    config = POC001Config(mesh=MeshConfig(characteristic_length_m=args.mesh_sizes[0], order=args.order))
    output = Path(args.output)
    points = run_mesh_convergence(
        config,
        output,
        characteristic_lengths_m=tuple(args.mesh_sizes),
        executables=executables,
    )
    gate = evaluate_poc001_gate(points)
    (output / "validation_gate.json").write_text(
        json.dumps(gate.as_dict(), indent=2), encoding="utf-8"
    )

    versions = solver_versions(executables)
    payload = {
        "solver_versions": {"gmsh": versions.gmsh, "getdp": versions.getdp},
        "finite_element_order": args.order,
        "convergence": [
            {
                "characteristic_length_m": p.characteristic_length_m,
                "nodes": p.node_count,
                "elements": p.element_count,
                **p.metrics,
            }
            for p in points
        ],
        "validation_gate": gate.as_dict(),
    }
    print(json.dumps(payload, indent=2))
    if not gate.passed:
        print("PVL-POC-001 validation gate: FAILED")
        return 3
    print("PVL-POC-001 validation gate: PASSED")
    return 0


def _cmd_poc002_fem(args: argparse.Namespace) -> int:
    try:
        executables = discover_executables()
    except SolverUnavailableError as exc:
        print(f"PVL FEM status: NOT READY — {exc}")
        return 2

    mesh = MeshConfig(characteristic_length_m=args.mesh_sizes[0], order=args.order)
    same = POC002Config(mesh=mesh)
    opposed = same.model_copy(
        update={"coil_b": same.coil_b.model_copy(update={"polarity": -1})}
    )
    output = Path(args.output)
    same_points = run_dual_mesh_convergence(
        same,
        output / "same_polarity",
        characteristic_lengths_m=tuple(args.mesh_sizes),
        executables=executables,
    )
    opposed_points = run_dual_mesh_convergence(
        opposed,
        output / "opposed_polarity",
        characteristic_lengths_m=tuple(args.mesh_sizes),
        executables=executables,
    )
    gate = evaluate_poc002_gate(same_points, opposed_points)
    output.mkdir(parents=True, exist_ok=True)
    (output / "validation_gate.json").write_text(
        json.dumps(gate.as_dict(), indent=2), encoding="utf-8"
    )

    versions = solver_versions(executables)
    payload = {
        "solver_versions": {"gmsh": versions.gmsh, "getdp": versions.getdp},
        "finite_element_order": args.order,
        "same_polarity_finest": same_points[-1].metrics,
        "opposed_polarity_finest": opposed_points[-1].metrics,
        "validation_gate": gate.as_dict(),
    }
    print(json.dumps(payload, indent=2))
    if not gate.passed:
        print("PVL-POC-002 dual-coil validation gate: FAILED")
        return 4
    print("PVL-POC-002 dual-coil validation gate: PASSED")
    return 0


def _cmd_poc003_phase(args: argparse.Namespace) -> int:
    config = POC003Config()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    reference = dual_coil_phasor_reference(config)
    gate = evaluate_poc003_gate()
    payload = {
        "experiment": config.model_dump(mode="json"),
        "configuration_hash": config.configuration_hash(),
        "baseline_phasor": [
            {
                "z_m": float(z),
                "real_t": float(value.real),
                "imag_t": float(value.imag),
                "peak_amplitude_t": float(abs(value)),
            }
            for z, value in zip(reference.z_m, reference.b_phasor_t)
        ],
        "validation_gate": gate.as_dict(),
        "established_physics_note": (
            "For scalar sinusoidal currents in the retained coaxial air-only geometry, the sign "
            "of omega is a frequency/phase representation convention, not by itself a distinct "
            "rotating magnetic-field state. A genuinely rotating field requires spatially "
            "non-collinear field components or another directional degree of freedom."
        ),
    }
    (output / "poc003_phase_gate.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, indent=2))
    if not gate.passed:
        print("PVL-POC-003 phase/frequency-sign validation gate: FAILED")
        return 5
    print("PVL-POC-003 phase/frequency-sign validation gate: PASSED")
    return 0


def _cmd_doctor(_: argparse.Namespace) -> int:
    try:
        executables = discover_executables()
    except SolverUnavailableError as exc:
        print(f"PVL FEM status: NOT READY — {exc}")
        return 2
    versions = solver_versions(executables)
    print(
        "PVL FEM status: READY — "
        f"gmsh={executables.gmsh} ({versions.gmsh}), "
        f"getdp={executables.getdp} ({versions.getdp})"
    )
    return 0


def _add_mesh_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--mesh-sizes",
        type=float,
        nargs="+",
        default=[0.03, 0.02, 0.012],
        help="global mesh characteristic lengths in metres",
    )
    parser.add_argument(
        "--order",
        type=int,
        choices=(1, 2),
        default=2,
        help="GetDP magnetic finite-element solution order used for the convergence study",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pvl")
    sub = parser.add_subparsers(dest="command", required=True)

    poc = sub.add_parser("poc001", help="generate POC-001 geometry and analytical reference")
    poc.add_argument("--output", default="results/poc001")
    poc.set_defaults(func=_cmd_poc001)

    fem = sub.add_parser("poc001-fem", help="run and gate the GetDP POC-001 convergence study")
    fem.add_argument("--output", default="results/poc001_fem")
    _add_mesh_arguments(fem)
    fem.set_defaults(func=_cmd_poc001_fem)

    dual = sub.add_parser(
        "poc002-fem",
        help="run and gate same/opposed independent dual-coil magnetostatic states",
    )
    dual.add_argument("--output", default="results/poc002_fem")
    _add_mesh_arguments(dual)
    dual.set_defaults(func=_cmd_poc002_fem)

    phase = sub.add_parser(
        "poc003-phase",
        help="validate dual-coil phase and signed-frequency conventions",
    )
    phase.add_argument("--output", default="results/poc003_phase")
    phase.set_defaults(func=_cmd_poc003_phase)

    doctor = sub.add_parser("doctor", help="check external FEM executables")
    doctor.set_defaults(func=_cmd_doctor)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
