from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np

from pvl.experiments.models import ExperimentConfig
from pvl.geometry.constructive import RigConstructiveTopology
from pvl.geometry.gmsh_rig import RigGmshConfig
from pvl.geometry.gmsh_rig_run import RigMeshRun, run_complete_rig_mesh
from pvl.materials.library import MaterialLibrary
from pvl.solvers.getdp.poc001_run import parse_getdp_axis_table
from pvl.solvers.getdp.rig_magnetostatic import build_winding_sources, write_rig_magnetostatic_pro
from pvl.solvers.getdp.runner import ExecutableSet, discover_executables, run_getdp, solver_versions


@dataclass(frozen=True)
class RigMagnetostaticResult:
    y_m: np.ndarray
    b_y_t: np.ndarray
    probe_y_m: np.ndarray
    probe_b_y_t: np.ndarray
    box_probe_y_m: np.ndarray
    box_probe_b_y_t: np.ndarray
    mesh_run: RigMeshRun
    pro_path: Path
    source_ampere_turns: tuple[float, float]
    solver_versions: dict[str, str]
    metrics: dict[str, float]


def _axis_metrics(y_m: np.ndarray, b_y_t: np.ndarray) -> dict[str, float]:
    if y_m.size == 0 or b_y_t.size != y_m.size:
        raise ValueError("complete-Rig magnetostatic axis result is empty or inconsistent")
    if not np.all(np.isfinite(y_m)) or not np.all(np.isfinite(b_y_t)):
        raise ValueError("complete-Rig magnetostatic axis result contains non-finite values")
    peak = float(np.max(np.abs(b_y_t)))
    center = float(np.interp(0.0, y_m, b_y_t)) if y_m[0] <= 0.0 <= y_m[-1] else float("nan")
    rms = float(np.sqrt(np.mean(np.square(b_y_t))))
    return {
        "axis_peak_abs_b_t": peak,
        "axis_rms_b_t": rms,
        "axis_center_b_y_t": center,
    }


def _read_exact_probes(
    output_dir: Path,
    requested_y_m: tuple[float, ...],
) -> tuple[np.ndarray, np.ndarray]:
    if not requested_y_m:
        return np.asarray([], dtype=float), np.asarray([], dtype=float)

    y_values: list[float] = []
    b_values: list[float] = []
    for index, expected_y in enumerate(requested_y_m):
        path = output_dir / f"b_probe_{index:03d}.txt"
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"GetDP completed without producing exact probe file: {path.name}")
        y_m, b_y_t = parse_getdp_axis_table(path)
        if y_m.size != 1 or b_y_t.size != 1:
            raise RuntimeError(f"exact complete-Rig point probe did not produce one sample: {path.name}")
        if not np.isclose(y_m[0], expected_y, rtol=0.0, atol=1e-10):
            raise RuntimeError(
                f"exact complete-Rig point probe coordinate mismatch: {path.name} "
                f"expected {expected_y:.17g}, got {y_m[0]:.17g}"
            )
        if not np.isfinite(b_y_t[0]):
            raise RuntimeError(f"exact complete-Rig point probe is non-finite: {path.name}")
        y_values.append(float(y_m[0]))
        b_values.append(float(b_y_t[0]))

    return np.asarray(y_values, dtype=float), np.asarray(b_values, dtype=float)


def _parse_getdp_vector_table(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Return xyz coordinates and vector values from a real-valued GetDP ``Format Table`` file."""
    coordinates: list[tuple[float, float, float]] = []
    vectors: list[tuple[float, float, float]] = []
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
        coordinates.append((values[2], values[3], values[4]))
        vectors.append((values[-3], values[-2], values[-1]))
    if not coordinates:
        raise ValueError(f"No numeric vector samples found in GetDP table: {path}")
    xyz = np.asarray(coordinates, dtype=float)
    vector = np.asarray(vectors, dtype=float)
    if not np.all(np.isfinite(xyz)) or not np.all(np.isfinite(vector)):
        raise ValueError(f"Non-finite vector samples found in GetDP table: {path}")
    return xyz, vector


def _read_box_probe_mean(
    path: Path,
    *,
    center_xyz_m: tuple[float, float, float],
    half_width_m: float,
) -> float:
    """Compute a tensor-trapezoidal volume mean of B_y from a fixed GetDP OnBox grid."""
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"GetDP completed without producing sensor-volume probe file: {path.name}")
    xyz, vector = _parse_getdp_vector_table(path)
    axes = [np.unique(xyz[:, index]) for index in range(3)]
    if any(axis.size < 2 for axis in axes):
        raise RuntimeError(f"sensor-volume probe grid is degenerate: {path.name}")
    expected_samples = int(np.prod([axis.size for axis in axes]))
    if xyz.shape[0] != expected_samples:
        raise RuntimeError(f"sensor-volume probe grid is incomplete or duplicated: {path.name}")

    center = np.asarray(center_xyz_m, dtype=float)
    for index, axis in enumerate(axes):
        if not np.isclose(axis[0], center[index] - half_width_m, rtol=0.0, atol=1e-9):
            raise RuntimeError(f"sensor-volume probe lower bound mismatch: {path.name}")
        if not np.isclose(axis[-1], center[index] + half_width_m, rtol=0.0, atol=1e-9):
            raise RuntimeError(f"sensor-volume probe upper bound mismatch: {path.name}")

    grid = np.full(tuple(axis.size for axis in axes), np.nan, dtype=float)
    for coordinate, by_value in zip(xyz, vector[:, 1]):
        indices: list[int] = []
        for axis, value in zip(axes, coordinate):
            position = int(np.searchsorted(axis, value))
            if position >= axis.size or not np.isclose(axis[position], value, rtol=0.0, atol=1e-12):
                raise RuntimeError(f"sensor-volume probe coordinate is off-grid: {path.name}")
            indices.append(position)
        key = tuple(indices)
        if np.isfinite(grid[key]):
            raise RuntimeError(f"sensor-volume probe grid contains duplicate coordinates: {path.name}")
        grid[key] = float(by_value)
    if not np.all(np.isfinite(grid)):
        raise RuntimeError(f"sensor-volume probe grid contains missing/non-finite values: {path.name}")

    integrated_z = np.trapezoid(grid, axes[2], axis=2)
    integrated_y = np.trapezoid(integrated_z, axes[1], axis=1)
    integral = float(np.trapezoid(integrated_y, axes[0], axis=0))
    volume = float(np.prod([axis[-1] - axis[0] for axis in axes]))
    if volume <= 0.0:
        raise RuntimeError(f"sensor-volume probe has non-positive sampled volume: {path.name}")
    mean = integral / volume
    if not np.isfinite(mean):
        raise RuntimeError(f"sensor-volume probe mean is non-finite: {path.name}")
    return float(mean)


def _read_box_probes(
    output_dir: Path,
    topology: RigConstructiveTopology,
    requested_y_m: tuple[float, ...],
    *,
    half_width_m: float,
) -> tuple[np.ndarray, np.ndarray]:
    if not requested_y_m:
        return np.asarray([], dtype=float), np.asarray([], dtype=float)
    chamber = next(item for item in topology.primitives if item.primitive_id == "sample:medium")
    px, _, pz = chamber.center_m
    means = [
        _read_box_probe_mean(
            output_dir / f"b_probe_box_{index:03d}.txt",
            center_xyz_m=(px, y_value, pz),
            half_width_m=half_width_m,
        )
        for index, y_value in enumerate(requested_y_m)
    ]
    return np.asarray(requested_y_m, dtype=float), np.asarray(means, dtype=float)


def run_complete_rig_dc_magnetostatic(
    experiment: ExperimentConfig,
    topology: RigConstructiveTopology,
    materials: MaterialLibrary,
    mesh_config: RigGmshConfig,
    output_dir: Path,
    *,
    executables: ExecutableSet | None = None,
    axis_samples: int = 101,
    probe_y_m: tuple[float, ...] = (),
    probe_box_y_m: tuple[float, ...] = (),
    probe_box_half_width_m: float = 0.002,
    probe_box_divisions: tuple[int, int, int] = (4, 4, 4),
) -> RigMagnetostaticResult:
    """Mesh and solve exactly one ordinary-physics complete-Rig DC state.

    This function is intentionally below the PVL-2N immutable-package execution boundary; PVL-2Q
    first uses it as a solver-validation primitive. Persisting an experiment result as an executed
    scientific run requires the separate single-run package/fingerprint gate.
    """
    exe = executables or discover_executables()
    output_dir.mkdir(parents=True, exist_ok=True)
    mesh_run = run_complete_rig_mesh(
        topology,
        mesh_config,
        output_dir / "mesh",
        gmsh_executable=exe.gmsh,
    )
    if not mesh_run.gate.passed:
        raise RuntimeError("complete-Rig mesh gate failed; GetDP execution is blocked")

    source_a, source_b = build_winding_sources(experiment, topology, mesh_run.gmsh_manifest)
    for source in (source_a, source_b):
        if not np.isclose(
            source.integrated_cross_section_current_a,
            source.ampere_turns,
            rtol=1e-14,
            atol=1e-14,
        ):
            raise RuntimeError(f"winding source normalization failed: {source.primitive_id}")

    pro_path = write_rig_magnetostatic_pro(
        experiment,
        topology,
        mesh_run.gmsh_manifest,
        materials,
        output_dir / "rig_dc.pro",
        axis_samples=axis_samples,
        probe_y_m=probe_y_m,
        probe_box_y_m=probe_box_y_m,
        probe_box_half_width_m=probe_box_half_width_m,
        probe_box_divisions=probe_box_divisions,
    )
    run = run_getdp(
        pro_path,
        mesh_run.mesh_path,
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
    if not axis_file.is_file() or axis_file.stat().st_size == 0:
        raise RuntimeError("GetDP completed without producing complete-Rig b_axis.txt")
    y_m, b_y_t = parse_getdp_axis_table(axis_file)
    exact_probe_y_m, exact_probe_b_y_t = _read_exact_probes(output_dir, probe_y_m)
    box_probe_y_m_values, box_probe_b_y_t = _read_box_probes(
        output_dir,
        topology,
        probe_box_y_m,
        half_width_m=probe_box_half_width_m,
    )
    metrics = _axis_metrics(y_m, b_y_t)
    if exact_probe_b_y_t.size:
        metrics["probe_peak_abs_b_t"] = float(np.max(np.abs(exact_probe_b_y_t)))
        zero_indices = np.flatnonzero(np.isclose(exact_probe_y_m, 0.0, rtol=0.0, atol=1e-14))
        if zero_indices.size == 1:
            metrics["probe_center_b_y_t"] = float(exact_probe_b_y_t[int(zero_indices[0])])
    if box_probe_b_y_t.size:
        metrics["box_probe_peak_abs_b_y_t"] = float(np.max(np.abs(box_probe_b_y_t)))
        zero_indices = np.flatnonzero(
            np.isclose(box_probe_y_m_values, 0.0, rtol=0.0, atol=1e-14)
        )
        if zero_indices.size == 1:
            metrics["box_probe_center_b_y_t"] = float(box_probe_b_y_t[int(zero_indices[0])])
    if metrics["axis_peak_abs_b_t"] <= 0.0 and any(
        abs(value) > 0.0 for value in (source_a.ampere_turns, source_b.ampere_turns)
    ):
        raise RuntimeError("active winding source produced a zero complete-Rig magnetic field")

    versions = solver_versions(exe)
    version_map = {"gmsh": versions.gmsh, "getdp": versions.getdp}
    payload = {
        "experiment": experiment.model_dump(mode="json"),
        "configuration_hash": experiment.configuration_hash(),
        "physics_state_hash": experiment.physics_state_hash(),
        "source_rig_fingerprint": topology.source_rig_fingerprint,
        "constructive_topology_fingerprint": topology.fingerprint_sha256(),
        "gmsh_configuration_hash": mesh_run.gmsh_manifest.gmsh_configuration_hash,
        "solver_versions": version_map,
        "source_normalization": [
            {
                "primitive_id": source.primitive_id,
                "turns": source.turns,
                "signed_current_a": source.signed_current_a,
                "ampere_turns": source.ampere_turns,
                "pack_cross_section_m2": source.pack_cross_section_m2,
                "current_density_a_m2": source.current_density_a_m2,
                "integrated_cross_section_current_a": source.integrated_cross_section_current_a,
                "geometric_axis_y_sign": source.geometric_axis_y_sign,
                "electrical_reference_y_sign": source.electrical_reference_y_sign,
            }
            for source in (source_a, source_b)
        ],
        "exact_probes": [
            {"y_m": float(y_value), "b_y_t": float(b_value)}
            for y_value, b_value in zip(exact_probe_y_m, exact_probe_b_y_t)
        ],
        "sensor_volume_probes": [
            {
                "center_y_m": float(y_value),
                "half_width_m": probe_box_half_width_m,
                "onbox_divisions": list(probe_box_divisions),
                "volume_mean_b_y_t": float(b_value),
            }
            for y_value, b_value in zip(box_probe_y_m_values, box_probe_b_y_t)
        ],
        "mesh_gate": mesh_run.gate.model_dump(mode="json"),
        "metrics": metrics,
        "scientific_boundary": (
            "Ordinary 3D DC magnetostatics only. Sensor-volume post-processing changes only the "
            "reported observable; conductivity-driven eddy currents, thermal effects, anomalies "
            "and Portal Hypothesis terms are absent."
        ),
    }
    (output_dir / "metrics.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    return RigMagnetostaticResult(
        y_m=y_m,
        b_y_t=b_y_t,
        probe_y_m=exact_probe_y_m,
        probe_b_y_t=exact_probe_b_y_t,
        box_probe_y_m=box_probe_y_m_values,
        box_probe_b_y_t=box_probe_b_y_t,
        mesh_run=mesh_run,
        pro_path=pro_path,
        source_ampere_turns=(source_a.ampere_turns, source_b.ampere_turns),
        solver_versions=version_map,
        metrics=metrics,
    )
