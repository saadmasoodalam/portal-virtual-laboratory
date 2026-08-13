from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np

from pvl.core.models import MeshConfig, POC001Config
from pvl.core.physics import relative_error
from pvl.geometry.poc001 import write_axisymmetric_gmsh_geo
from pvl.solvers.getdp.poc001 import write_magnetostatic_pro
from pvl.solvers.getdp.runner import (
    ExecutableSet,
    discover_executables,
    generate_mesh,
    run_getdp,
    solver_versions,
)
from pvl.validation.poc001 import (
    analytical_reference,
    compare_fem_to_analytic,
    finite_source_reference,
)


@dataclass(frozen=True)
class FEMAxisResult:
    z_m: np.ndarray
    b_axis_t: np.ndarray
    raw_axis_file: Path
    mesh_file: Path
    metrics: dict[str, float]
    node_count: int
    element_count: int


@dataclass(frozen=True)
class ConvergencePoint:
    characteristic_length_m: float
    metrics: dict[str, float]
    b_axis_t: tuple[float, ...]
    node_count: int
    element_count: int


def parse_getdp_axis_table(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Parse a GetDP ``Format Table`` vector-field cut.

    GetDP table rows begin with element metadata and x/y/z coordinates and end with the
    evaluated vector components. The POC's physical axis is the y-axis, so the returned field
    component is B_y, i.e. the second of the final three vector values.
    """
    y_values: list[float] = []
    by_values: list[float] = []
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            values = [float(token) for token in line.replace(",", " ").split()]
        except ValueError:
            continue
        if len(values) < 8:
            continue
        # GetDP Table format starts with element type/index then x y z. The final three
        # numeric entries are vector components for a real-valued vector field.
        y_values.append(values[3])
        by_values.append(values[-2])

    if not y_values:
        raise ValueError(f"No numeric vector samples found in GetDP table: {path}")

    y = np.asarray(y_values, dtype=float)
    by = np.asarray(by_values, dtype=float)
    order = np.argsort(y)
    return y[order], by[order]


def parse_msh2_counts(path: Path) -> tuple[int, int]:
    """Return node and element counts from an ASCII Gmsh MSH 2.x file."""
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    try:
        node_marker = lines.index("$Nodes")
        element_marker = lines.index("$Elements")
        return int(lines[node_marker + 1]), int(lines[element_marker + 1])
    except (ValueError, IndexError) as exc:
        raise ValueError(f"Could not read MSH2 entity counts from {path}") from exc


def _symmetry_error(z_m: np.ndarray, field: np.ndarray) -> float | None:
    if z_m.size < 2 or not np.allclose(z_m, -z_m[::-1], rtol=0.0, atol=1e-14):
        return None
    left = field
    right = field[::-1]
    scale = np.maximum((np.abs(left) + np.abs(right)) / 2.0, np.finfo(float).tiny)
    return float(np.max(np.abs(left - right) / scale))


def run_axisymmetric_poc001(
    config: POC001Config,
    output_dir: Path,
    *,
    executables: ExecutableSet | None = None,
) -> FEMAxisResult:
    """Generate, mesh, solve, post-process and validate one PVL-POC-001 FEM case."""
    exe = executables or discover_executables()
    output_dir.mkdir(parents=True, exist_ok=True)

    geo = write_axisymmetric_gmsh_geo(config, output_dir / "poc001_axi.geo")
    pro = write_magnetostatic_pro(config, output_dir / "poc001_axi.pro")
    mesh = generate_mesh(
        geo,
        dimension=2,
        output_path=output_dir / "poc001_axi.msh",
        executables=exe,
    )
    node_count, element_count = parse_msh2_counts(mesh)
    run = run_getdp(
        pro,
        mesh,
        resolution="Mag",
        post_operation="Axis",
        executables=exe,
    )

    (output_dir / "solver_stdout.log").write_text(
        run.solve_stdout + "\n--- POST ---\n" + run.post_stdout,
        encoding="utf-8",
    )
    (output_dir / "solver_stderr.log").write_text(
        run.solve_stderr + "\n--- POST ---\n" + run.post_stderr,
        encoding="utf-8",
    )

    axis_file = output_dir / "b_axis.txt"
    if not axis_file.exists() or axis_file.stat().st_size == 0:
        raise RuntimeError("GetDP completed without producing b_axis.txt")

    raw_y, raw_by = parse_getdp_axis_table(axis_file)
    target_z = np.asarray(config.probe_z_m, dtype=float)
    fem_by = np.interp(target_z, raw_y, raw_by)

    # Match the numerical source exactly: the FEM uses a finite rectangular winding
    # section. The textbook filament result remains an independent secondary oracle.
    finite_reference = finite_source_reference(config)
    filament_reference = analytical_reference(config)
    metrics = compare_fem_to_analytic(finite_reference, fem_by)
    symmetry = _symmetry_error(target_z, fem_by)
    if symmetry is not None:
        metrics["symmetry_max_relative_difference"] = symmetry
    source_model_errors = relative_error(filament_reference.b_t, finite_reference.b_t)

    versions = solver_versions(exe)
    summary = {
        "experiment": config.model_dump(mode="json"),
        "configuration_hash": config.configuration_hash(),
        "solver_versions": {"gmsh": versions.gmsh, "getdp": versions.getdp},
        "mesh": {"nodes": node_count, "elements": element_count},
        "reference_model": "finite rectangular winding section",
        "filament_vs_finite_source": {
            "max_relative_difference": float(np.max(source_model_errors)),
            "mean_relative_difference": float(np.mean(source_model_errors)),
        },
        "probe_results": [
            {
                "z_m": float(z),
                "fem_b_axis_t": float(fem),
                "finite_source_b_axis_t": float(finite),
                "filament_b_axis_t": float(filament),
            }
            for z, fem, finite, filament in zip(
                target_z, fem_by, finite_reference.b_t, filament_reference.b_t
            )
        ],
        "metrics": metrics,
    }
    (output_dir / "metrics.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    return FEMAxisResult(
        z_m=target_z,
        b_axis_t=fem_by,
        raw_axis_file=axis_file,
        mesh_file=mesh,
        metrics=metrics,
        node_count=node_count,
        element_count=element_count,
    )


def run_mesh_convergence(
    base_config: POC001Config,
    output_dir: Path,
    *,
    characteristic_lengths_m: tuple[float, ...] = (0.03, 0.02, 0.012),
    executables: ExecutableSet | None = None,
) -> list[ConvergencePoint]:
    """Run the same physical case at successively finer global mesh sizes."""
    if len(characteristic_lengths_m) < 2:
        raise ValueError("mesh convergence requires at least two mesh sizes")
    if any(a <= b for a, b in zip(characteristic_lengths_m, characteristic_lengths_m[1:])):
        raise ValueError("mesh sizes must be strictly descending from coarse to fine")

    exe = executables or discover_executables()
    points: list[ConvergencePoint] = []
    for index, h in enumerate(characteristic_lengths_m, start=1):
        config = base_config.model_copy(
            update={"mesh": MeshConfig(characteristic_length_m=h, order=base_config.mesh.order)}
        )
        result = run_axisymmetric_poc001(config, output_dir / f"mesh_{index:02d}", executables=exe)
        points.append(
            ConvergencePoint(
                characteristic_length_m=h,
                metrics=result.metrics,
                b_axis_t=tuple(float(value) for value in result.b_axis_t),
                node_count=result.node_count,
                element_count=result.element_count,
            )
        )

    payload = []
    previous: np.ndarray | None = None
    for point in points:
        field = np.asarray(point.b_axis_t, dtype=float)
        change = None
        if previous is not None:
            denominator = np.maximum(np.abs(previous), np.finfo(float).tiny)
            change = float(np.max(np.abs(field - previous) / denominator))
        payload.append(
            {
                "characteristic_length_m": point.characteristic_length_m,
                "nodes": point.node_count,
                "elements": point.element_count,
                "successive_max_relative_field_change": change,
                **point.metrics,
            }
        )
        previous = field

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "convergence.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return points
