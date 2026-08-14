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
from pvl.solvers.getdp.rig_magnetothermal import write_rig_magnetothermal_pro
from pvl.solvers.getdp.rig_magnetoquasistatic import (
    RigMagnetoquasistaticModel,
    build_rig_magnetoquasistatic_model,
)
from pvl.solvers.getdp.runner import ExecutableSet, discover_executables, run_getdp, solver_versions


@dataclass(frozen=True)
class RigMagnetothermalResult:
    y_m: np.ndarray
    temperature_k: np.ndarray
    probe_y_m: np.ndarray
    probe_temperature_k: np.ndarray
    joule_input_w: float
    mesh_run: RigMeshRun
    pro_path: Path
    mq_model: RigMagnetoquasistaticModel
    solver_versions: dict[str, str]
    metrics: dict[str, float]


def parse_getdp_real_system_scalar_line(
    path: Path,
    *,
    coordinate_column: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Parse one coordinate and scalar emitted by a real-valued GetDP system.

    Complex GetDP post-processing stores an explicitly real scalar as a final real/imaginary pair,
    which is why POC-005 reads the penultimate column. The thermal system is genuinely real and
    GetDP serializes its scalar as the *last* numeric column. Reusing the complex parser therefore
    reads a metadata/zero column instead of temperature. This parser makes that format distinction
    explicit so a numerically valid thermal solve cannot be rejected by post-processing.
    """
    coordinates: list[float] = []
    scalars: list[float] = []
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            values = [float(token) for token in line.replace(",", " ").split()]
        except ValueError:
            continue
        if len(values) < 5 or coordinate_column >= len(values):
            continue
        coordinates.append(values[coordinate_column])
        scalars.append(values[-1])
    if not coordinates:
        raise ValueError(f"No real scalar line samples found in GetDP table: {path}")
    coordinate = np.asarray(coordinates, dtype=float)
    field = np.asarray(scalars, dtype=float)
    order = np.argsort(coordinate)
    return coordinate[order], field[order]


def parse_getdp_real_system_global(path: Path) -> float:
    """Parse one scalar emitted by a real-valued GetDP OnGlobal operation."""
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            values = [float(token) for token in line.replace(",", " ").split()]
        except ValueError:
            continue
        if values:
            return float(values[-1])
    raise ValueError(f"No real global scalar found in GetDP table: {path}")


def _read_temperature_probes(
    output_dir: Path,
    requested_y_m: tuple[float, ...],
) -> tuple[np.ndarray, np.ndarray]:
    if not requested_y_m:
        return np.asarray([], dtype=float), np.asarray([], dtype=float)
    positions: list[float] = []
    values: list[float] = []
    for index, expected_y in enumerate(requested_y_m):
        path = output_dir / f"temperature_probe_{index:03d}.txt"
        if not path.is_file():
            raise RuntimeError(f"complete-Rig thermal probe output missing: {index}")
        y, temperature = parse_getdp_real_system_scalar_line(path, coordinate_column=3)
        if y.size != 1 or temperature.size != 1:
            raise RuntimeError(f"complete-Rig thermal point probe did not produce one sample: {index}")
        if not np.isclose(y[0], expected_y, rtol=0.0, atol=1e-10):
            raise RuntimeError(f"complete-Rig thermal point coordinate mismatch: {index}")
        if not np.isfinite(temperature[0]):
            raise RuntimeError(f"complete-Rig thermal point is non-finite: {index}")
        positions.append(float(expected_y))
        values.append(float(temperature[0]))
    return np.asarray(positions, dtype=float), np.asarray(values, dtype=float)


def run_complete_rig_steady_magnetothermal(
    experiment: ExperimentConfig,
    topology: RigConstructiveTopology,
    materials: MaterialLibrary,
    mesh_config: RigGmshConfig,
    output_dir: Path,
    *,
    ambient_temperature_k: float = 293.15,
    executables: ExecutableSet | None = None,
    axis_samples: int = 101,
    probe_y_m: tuple[float, ...] = (),
) -> RigMagnetothermalResult:
    """Run one-way MQ -> steady conduction coupling on the complete exploratory Rig."""
    exe = executables or discover_executables()
    output_dir.mkdir(parents=True, exist_ok=True)
    mesh_run = run_complete_rig_mesh(
        topology,
        mesh_config,
        output_dir / "mesh",
        gmsh_executable=exe.gmsh,
    )
    if not mesh_run.gate.passed:
        raise RuntimeError("complete-Rig mesh gate failed; magneto-thermal execution is blocked")

    mq_model = build_rig_magnetoquasistatic_model(
        experiment,
        topology,
        mesh_run.gmsh_manifest,
        materials,
    )
    pro_path = write_rig_magnetothermal_pro(
        experiment,
        topology,
        mesh_run.gmsh_manifest,
        materials,
        output_dir / "rig_magthe.pro",
        ambient_temperature_k=ambient_temperature_k,
        axis_samples=axis_samples,
        probe_y_m=probe_y_m,
    )
    run = run_getdp(
        pro_path,
        mesh_run.mesh_path,
        resolution="MagThe",
        post_operation="ThermalDiagnostics",
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

    y_m, temperature_k = parse_getdp_real_system_scalar_line(
        output_dir / "temperature_axis.txt",
        coordinate_column=3,
    )
    if y_m.size == 0 or temperature_k.size != y_m.size:
        raise RuntimeError("complete-Rig thermal axis result is empty or inconsistent")
    if not np.all(np.isfinite(y_m)) or not np.all(np.isfinite(temperature_k)):
        raise RuntimeError("complete-Rig thermal axis result contains non-finite values")
    probe_positions, probe_temperature = _read_temperature_probes(output_dir, probe_y_m)
    joule_input_w = parse_getdp_real_system_global(output_dir / "thermal_joule_input.txt")
    if not np.isfinite(joule_input_w) or joule_input_w < -1e-12:
        raise RuntimeError(f"complete-Rig thermal Joule input is invalid: {joule_input_w}")
    joule_input_w = max(0.0, float(joule_input_w))

    minimum_temperature = float(np.min(temperature_k))
    maximum_temperature = float(np.max(temperature_k))
    if minimum_temperature < ambient_temperature_k - 1e-5:
        raise RuntimeError(
            "positive-Joule steady conduction solve produced temperature below the fixed ambient boundary"
        )
    center_temperature = (
        float(np.interp(0.0, y_m, temperature_k))
        if y_m[0] <= 0.0 <= y_m[-1]
        else float("nan")
    )
    metrics = {
        "frequency_hz": mq_model.frequency_hz,
        "ambient_temperature_k": float(ambient_temperature_k),
        "axis_min_temperature_k": minimum_temperature,
        "axis_max_temperature_k": maximum_temperature,
        "axis_peak_delta_temperature_k": maximum_temperature - ambient_temperature_k,
        "axis_center_temperature_k": center_temperature,
        "axis_center_delta_temperature_k": center_temperature - ambient_temperature_k,
        "joule_input_w": joule_input_w,
    }
    if probe_temperature.size:
        metrics["probe_max_temperature_k"] = float(np.max(probe_temperature))
        metrics["probe_peak_delta_temperature_k"] = float(
            np.max(probe_temperature) - ambient_temperature_k
        )

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
        "frequency_hz": mq_model.frequency_hz,
        "ambient_temperature_k": ambient_temperature_k,
        "thermal_environment_model": "conduction_only_with_fixed_remote_air_boundary",
        "metrics": metrics,
        "mesh_gate": mesh_run.gate.model_dump(mode="json"),
        "scientific_boundary": (
            "One-way ordinary magneto-quasistatic Joule heating into steady thermal conduction. "
            "Air convection, radiation, conductivity-temperature feedback, biological response, "
            "anomaly classification and Portal Hypothesis terms are absent."
        ),
    }
    (output_dir / "metrics.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return RigMagnetothermalResult(
        y_m=y_m,
        temperature_k=temperature_k,
        probe_y_m=probe_positions,
        probe_temperature_k=probe_temperature,
        joule_input_w=joule_input_w,
        mesh_run=mesh_run,
        pro_path=pro_path,
        mq_model=mq_model,
        solver_versions=version_map,
        metrics=metrics,
    )
