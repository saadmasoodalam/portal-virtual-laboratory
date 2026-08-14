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
from pvl.solvers.getdp.poc005_run import parse_getdp_global_real, parse_getdp_real_scalar_line
from pvl.solvers.getdp.rig_magnetoquasistatic import (
    RigMagnetoquasistaticModel,
    build_rig_magnetoquasistatic_model,
    write_rig_magnetoquasistatic_pro,
)
from pvl.solvers.getdp.runner import ExecutableSet, discover_executables, run_getdp, solver_versions


@dataclass(frozen=True)
class RigMagnetoquasistaticResult:
    y_m: np.ndarray
    b_y_t: np.ndarray
    probe_y_m: np.ndarray
    probe_b_y_t: np.ndarray
    joule_loss_w: float
    mesh_run: RigMeshRun
    pro_path: Path
    model: RigMagnetoquasistaticModel
    solver_versions: dict[str, str]
    metrics: dict[str, float]


def _load_complex_scalar_line(
    output_dir: Path,
    real_name: str,
    imag_name: str,
) -> tuple[np.ndarray, np.ndarray]:
    y_re, real = parse_getdp_real_scalar_line(
        output_dir / real_name,
        coordinate_column=3,
    )
    y_im, imag = parse_getdp_real_scalar_line(
        output_dir / imag_name,
        coordinate_column=3,
    )
    if not np.allclose(y_re, y_im, rtol=0.0, atol=1e-12):
        raise RuntimeError(f"complete-Rig harmonic real/imag coordinates differ: {real_name}, {imag_name}")
    field = real + 1j * imag
    if not np.all(np.isfinite(y_re)) or not np.all(np.isfinite(field)):
        raise RuntimeError("complete-Rig harmonic axis contains non-finite values")
    return y_re, field


def _read_complex_exact_probes(
    output_dir: Path,
    requested_y_m: tuple[float, ...],
) -> tuple[np.ndarray, np.ndarray]:
    if not requested_y_m:
        return np.asarray([], dtype=float), np.asarray([], dtype=complex)
    positions: list[float] = []
    fields: list[complex] = []
    for index, expected_y in enumerate(requested_y_m):
        real_path = output_dir / f"by_probe_re_{index:03d}.txt"
        imag_path = output_dir / f"by_probe_im_{index:03d}.txt"
        if not real_path.is_file() or not imag_path.is_file():
            raise RuntimeError(f"complete-Rig harmonic exact probe output missing at index {index}")
        y_re, real = parse_getdp_real_scalar_line(real_path, coordinate_column=3)
        y_im, imag = parse_getdp_real_scalar_line(imag_path, coordinate_column=3)
        if y_re.size != 1 or y_im.size != 1 or real.size != 1 or imag.size != 1:
            raise RuntimeError(f"complete-Rig harmonic point probe did not produce one sample: {index}")
        if not np.isclose(y_re[0], expected_y, rtol=0.0, atol=1e-10):
            raise RuntimeError(f"complete-Rig harmonic real probe coordinate mismatch: {index}")
        if not np.isclose(y_im[0], expected_y, rtol=0.0, atol=1e-10):
            raise RuntimeError(f"complete-Rig harmonic imaginary probe coordinate mismatch: {index}")
        value = complex(float(real[0]), float(imag[0]))
        if not np.isfinite(value.real) or not np.isfinite(value.imag):
            raise RuntimeError(f"complete-Rig harmonic point probe is non-finite: {index}")
        positions.append(float(expected_y))
        fields.append(value)
    return np.asarray(positions, dtype=float), np.asarray(fields, dtype=complex)


def _complex_axis_metrics(y_m: np.ndarray, b_y_t: np.ndarray) -> dict[str, float]:
    if y_m.size == 0 or b_y_t.size != y_m.size:
        raise ValueError("complete-Rig harmonic axis result is empty or inconsistent")
    magnitude = np.abs(b_y_t)
    center = (
        complex(
            np.interp(0.0, y_m, np.real(b_y_t)),
            np.interp(0.0, y_m, np.imag(b_y_t)),
        )
        if y_m[0] <= 0.0 <= y_m[-1]
        else complex(float("nan"), float("nan"))
    )
    return {
        "axis_peak_abs_b_t": float(np.max(magnitude)),
        "axis_rms_abs_b_t": float(np.sqrt(np.mean(np.square(magnitude)))),
        "axis_center_b_re_t": float(center.real),
        "axis_center_b_im_t": float(center.imag),
        "axis_center_abs_b_t": float(abs(center)),
    }


def run_complete_rig_harmonic_magnetoquasistatic(
    experiment: ExperimentConfig,
    topology: RigConstructiveTopology,
    materials: MaterialLibrary,
    mesh_config: RigGmshConfig,
    output_dir: Path,
    *,
    executables: ExecutableSet | None = None,
    axis_samples: int = 101,
    probe_y_m: tuple[float, ...] = (),
) -> RigMagnetoquasistaticResult:
    """Mesh, solve and post-process one complete-Rig harmonic established-physics state."""
    exe = executables or discover_executables()
    output_dir.mkdir(parents=True, exist_ok=True)
    mesh_run = run_complete_rig_mesh(
        topology,
        mesh_config,
        output_dir / "mesh",
        gmsh_executable=exe.gmsh,
    )
    if not mesh_run.gate.passed:
        raise RuntimeError("complete-Rig mesh gate failed; harmonic GetDP execution is blocked")

    model = build_rig_magnetoquasistatic_model(
        experiment,
        topology,
        mesh_run.gmsh_manifest,
        materials,
    )
    for source in (model.source_a.spatial, model.source_b.spatial):
        if not np.isclose(
            source.integrated_cross_section_current_a,
            source.ampere_turns,
            rtol=1e-14,
            atol=1e-14,
        ):
            raise RuntimeError(f"harmonic winding source normalization failed: {source.primitive_id}")

    pro_path = write_rig_magnetoquasistatic_pro(
        experiment,
        topology,
        mesh_run.gmsh_manifest,
        materials,
        output_dir / "rig_mq.pro",
        axis_samples=axis_samples,
        probe_y_m=probe_y_m,
    )
    run = run_getdp(
        pro_path,
        mesh_run.mesh_path,
        resolution="MQ",
        post_operation="Diagnostics",
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

    y_m, b_y_t = _load_complex_scalar_line(
        output_dir,
        "by_axis_re.txt",
        "by_axis_im.txt",
    )
    exact_probe_y_m, exact_probe_b_y_t = _read_complex_exact_probes(output_dir, probe_y_m)
    joule_loss = parse_getdp_global_real(output_dir / "joule_losses.txt")
    if not np.isfinite(joule_loss) or joule_loss < -1e-12:
        raise RuntimeError(f"complete-Rig harmonic Joule loss is invalid: {joule_loss}")
    joule_loss = max(0.0, float(joule_loss))

    metrics = _complex_axis_metrics(y_m, b_y_t)
    metrics["frequency_hz"] = model.frequency_hz
    metrics["joule_loss_w"] = joule_loss
    if exact_probe_b_y_t.size:
        metrics["probe_peak_abs_b_t"] = float(np.max(np.abs(exact_probe_b_y_t)))
        zero_indices = np.flatnonzero(np.isclose(exact_probe_y_m, 0.0, rtol=0.0, atol=1e-14))
        if zero_indices.size == 1:
            center_probe = exact_probe_b_y_t[int(zero_indices[0])]
            metrics["probe_center_b_re_t"] = float(center_probe.real)
            metrics["probe_center_b_im_t"] = float(center_probe.imag)
            metrics["probe_center_abs_b_t"] = float(abs(center_probe))
    if metrics["axis_peak_abs_b_t"] <= 0.0 and any(
        abs(source.spatial.ampere_turns) > 0.0 for source in (model.source_a, model.source_b)
    ):
        raise RuntimeError("active harmonic winding source produced a zero complete-Rig magnetic field")

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
        "frequency_hz": model.frequency_hz,
        "sources": [
            {
                "primitive_id": source.spatial.primitive_id,
                "ampere_turns": source.spatial.ampere_turns,
                "current_density_a_m2": source.spatial.current_density_a_m2,
                "phase_rad": source.phase_rad,
                "omega_sign_mapping": "canonical_positive_frequency_phase_only",
            }
            for source in (model.source_a, model.source_b)
        ],
        "passive_conductors": [
            {
                "primitive_id": region.primitive_id,
                "material_id": region.material_id,
                "conductivity_s_m": region.conductivity_s_m,
            }
            for region in model.conductors
        ],
        "exact_probes": [
            {
                "y_m": float(y_value),
                "b_re_t": float(value.real),
                "b_im_t": float(value.imag),
                "b_abs_t": float(abs(value)),
            }
            for y_value, value in zip(exact_probe_y_m, exact_probe_b_y_t)
        ],
        "mesh_gate": mesh_run.gate.model_dump(mode="json"),
        "metrics": metrics,
        "scientific_boundary": (
            "Ordinary frequency-domain magneto-quasistatics with passive eddy currents and "
            "time-averaged Joule loss. No thermal feedback, biological model, anomaly classifier "
            "or Portal Hypothesis term is present."
        ),
    }
    (output_dir / "metrics.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return RigMagnetoquasistaticResult(
        y_m=y_m,
        b_y_t=b_y_t,
        probe_y_m=exact_probe_y_m,
        probe_b_y_t=exact_probe_b_y_t,
        joule_loss_w=joule_loss,
        mesh_run=mesh_run,
        pro_path=pro_path,
        model=model,
        solver_versions=version_map,
        metrics=metrics,
    )
