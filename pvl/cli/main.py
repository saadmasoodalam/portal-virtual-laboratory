from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

from pvl.core.models import MeshConfig, POC001Config, POC002Config, POC003Config
from pvl.core.poc004_models import POC004Config
from pvl.core.poc005_models import ConductiveInsertConfig, POC005Config
from pvl.geometry.poc001 import write_gmsh_geo
from pvl.solvers.getdp.poc001_run import evaluate_poc001_gate, run_mesh_convergence
from pvl.solvers.getdp.poc002_run import evaluate_poc002_gate, run_dual_mesh_convergence
from pvl.solvers.getdp.poc004_run import evaluate_poc004_gate, run_slab_mesh_convergence
from pvl.solvers.getdp.poc005_run import (
    evaluate_poc005_gate,
    run_conductive_insert_case,
    run_insert_mesh_convergence,
    vacuum_reference_error,
)
from pvl.solvers.getdp.runner import SolverUnavailableError, discover_executables, solver_versions
from pvl.validation.poc001 import analytical_reference
from pvl.validation.poc003 import dual_coil_phasor_reference, evaluate_poc003_gate
from pvl.validation.poc004 import skin_depth_m


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


def _cmd_poc004_eddy(args: argparse.Namespace) -> int:
    try:
        executables = discover_executables()
    except SolverUnavailableError as exc:
        print(f"PVL FEM status: NOT READY — {exc}")
        return 2

    config = POC004Config(
        frequency_hz=args.frequency,
        conductivity_s_m=args.conductivity,
        relative_permeability=args.relative_permeability,
        mesh=MeshConfig(characteristic_length_m=args.mesh_sizes[0], order=args.order),
    )
    output = Path(args.output)
    points = run_slab_mesh_convergence(
        config,
        output,
        characteristic_lengths_m=tuple(args.mesh_sizes),
        executables=executables,
    )
    gate = evaluate_poc004_gate(points)
    output.mkdir(parents=True, exist_ok=True)
    (output / "validation_gate.json").write_text(
        json.dumps(gate.as_dict(), indent=2), encoding="utf-8"
    )
    versions = solver_versions(executables)
    payload = {
        "solver_versions": {"gmsh": versions.gmsh, "getdp": versions.getdp},
        "finite_element_order": args.order,
        "frequency_hz": config.frequency_hz,
        "conductivity_s_m": config.conductivity_s_m,
        "relative_permeability": config.relative_permeability,
        "skin_depth_m": skin_depth_m(config),
        "finest_metrics": points[-1].metrics,
        "validation_gate": gate.as_dict(),
    }
    print(json.dumps(payload, indent=2))
    if not gate.passed:
        print("PVL-POC-004 eddy-current slab validation gate: FAILED")
        return 6
    print("PVL-POC-004 eddy-current slab validation gate: PASSED")
    return 0


def _cmd_poc005_insert(args: argparse.Namespace) -> int:
    try:
        executables = discover_executables()
    except SolverUnavailableError as exc:
        print(f"PVL FEM status: NOT READY — {exc}")
        return 2

    mesh = MeshConfig(characteristic_length_m=args.mesh_sizes[0], order=args.order)
    insert = ConductiveInsertConfig(
        conductivity_s_m=args.conductivity,
        relative_permeability=args.relative_permeability,
    )
    same = POC005Config(insert=insert, mesh=mesh)
    same = same.model_copy(
        update={
            "drive_a": same.drive_a.model_copy(update={"frequency_hz": args.frequency}),
            "drive_b": same.drive_b.model_copy(update={"frequency_hz": args.frequency}),
        }
    )
    opposed = same.model_copy(
        update={"drive_b": same.drive_b.model_copy(update={"phase_rad": math.pi})}
    )
    output = Path(args.output)

    same_points = run_insert_mesh_convergence(
        same,
        output / "conductive_same_phase",
        characteristic_lengths_m=tuple(args.mesh_sizes),
        executables=executables,
    )
    opposed_points = run_insert_mesh_convergence(
        opposed,
        output / "conductive_opposed_phase",
        characteristic_lengths_m=tuple(args.mesh_sizes),
        executables=executables,
    )

    validation_h = args.vacuum_mesh_size
    validation_mesh = MeshConfig(characteristic_length_m=validation_h, order=args.order)
    vacuum_insert = same.insert.model_copy(update={"conductivity_s_m": 0.0, "relative_permeability": 1.0})
    vacuum_same_config = same.model_copy(update={"insert": vacuum_insert, "mesh": validation_mesh})
    vacuum_opposed_config = opposed.model_copy(update={"insert": vacuum_insert, "mesh": validation_mesh})
    vacuum_same_result = run_conductive_insert_case(
        vacuum_same_config,
        output / "vacuum_control_same_phase",
        executables=executables,
    )
    vacuum_opposed_result = run_conductive_insert_case(
        vacuum_opposed_config,
        output / "vacuum_control_opposed_phase",
        executables=executables,
    )
    vacuum_same_metrics = vacuum_reference_error(vacuum_same_config, vacuum_same_result)
    vacuum_opposed_metrics = vacuum_reference_error(vacuum_opposed_config, vacuum_opposed_result)

    finest_h = args.mesh_sizes[-1]
    finest_mesh = MeshConfig(characteristic_length_m=finest_h, order=args.order)
    a_only_config = same.model_copy(
        update={
            "mesh": finest_mesh,
            "coil_b": same.coil_b.model_copy(update={"current_a": 0.0}),
        }
    )
    b_only_config = same.model_copy(
        update={
            "mesh": finest_mesh,
            "coil_a": same.coil_a.model_copy(update={"current_a": 0.0}),
        }
    )
    a_only = run_conductive_insert_case(
        a_only_config,
        output / "linearity_a_only",
        executables=executables,
    )
    b_only = run_conductive_insert_case(
        b_only_config,
        output / "linearity_b_only",
        executables=executables,
    )
    combined_b = np.asarray(same_points[-1].b_axis_t, dtype=complex)
    combined_j = np.asarray(same_points[-1].j_insert_a_m2, dtype=complex)
    expected_b = a_only.b_axis_t + b_only.b_axis_t
    expected_j = a_only.j_insert_a_m2 + b_only.j_insert_a_m2
    b_scale = max(float(np.max(np.abs(expected_b))), np.finfo(float).tiny)
    j_scale = max(float(np.max(np.abs(expected_j))), np.finfo(float).tiny)
    superposition = {
        "b_max_peak_normalized_superposition_error": float(
            np.max(np.abs(combined_b - expected_b)) / b_scale
        ),
        "j_max_peak_normalized_superposition_error": float(
            np.max(np.abs(combined_j - expected_j)) / j_scale
        ),
    }

    gate = evaluate_poc005_gate(
        same_points,
        opposed_points,
        vacuum_same_metrics,
        vacuum_opposed_metrics,
        superposition,
    )
    output.mkdir(parents=True, exist_ok=True)
    (output / "validation_gate.json").write_text(
        json.dumps(gate.as_dict(), indent=2), encoding="utf-8"
    )
    versions = solver_versions(executables)
    payload = {
        "solver_versions": {"gmsh": versions.gmsh, "getdp": versions.getdp},
        "finite_element_order": args.order,
        "frequency_hz": same.frequency_hz,
        "insert_conductivity_s_m": same.insert.conductivity_s_m,
        "insert_relative_permeability": same.insert.relative_permeability,
        "insert_skin_depth_m": same.insert_skin_depth_m,
        "vacuum_same_metrics": vacuum_same_metrics,
        "vacuum_opposed_metrics": vacuum_opposed_metrics,
        "superposition_metrics": superposition,
        "same_finest_joule_loss_w": same_points[-1].joule_loss_w,
        "opposed_finest_joule_loss_w": opposed_points[-1].joule_loss_w,
        "validation_gate": gate.as_dict(),
    }
    (output / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    if not gate.passed:
        print("PVL-POC-005 dual-coil conductive-insert validation gate: FAILED")
        return 7
    print("PVL-POC-005 dual-coil conductive-insert validation gate: PASSED")
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

    eddy = sub.add_parser(
        "poc004-eddy",
        help="run and gate the exact conducting-slab magnetic-diffusion benchmark",
    )
    eddy.add_argument("--output", default="results/poc004_eddy")
    eddy.add_argument(
        "--mesh-sizes",
        type=float,
        nargs="+",
        default=[0.001, 0.0005, 0.00025],
        help="strictly descending slab mesh characteristic lengths in metres",
    )
    eddy.add_argument("--order", type=int, choices=(1, 2), default=2)
    eddy.add_argument("--frequency", type=float, default=1000.0, help="frequency in hertz")
    eddy.add_argument(
        "--conductivity",
        type=float,
        default=5.8e7,
        help="conductor conductivity in siemens per metre",
    )
    eddy.add_argument(
        "--relative-permeability",
        type=float,
        default=1.0,
        help="linear relative permeability for the validation slab",
    )
    eddy.set_defaults(func=_cmd_poc004_eddy)

    insert = sub.add_parser(
        "poc005-insert",
        help="run and gate the harmonic dual-coil conductive-insert integration benchmark",
    )
    insert.add_argument("--output", default="results/poc005_insert")
    insert.add_argument(
        "--mesh-sizes",
        type=float,
        nargs="+",
        default=[0.01, 0.007, 0.005],
        help="strictly descending far-field mesh sizes in metres",
    )
    insert.add_argument("--vacuum-mesh-size", type=float, default=0.007)
    insert.add_argument("--order", type=int, choices=(1, 2), default=2)
    insert.add_argument("--frequency", type=float, default=1000.0)
    insert.add_argument("--conductivity", type=float, default=5.8e7)
    insert.add_argument("--relative-permeability", type=float, default=1.0)
    insert.set_defaults(func=_cmd_poc005_insert)

    doctor = sub.add_parser("doctor", help="check external FEM executables")
    doctor.set_defaults(func=_cmd_doctor)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
