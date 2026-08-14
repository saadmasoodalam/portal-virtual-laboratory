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


def run_complete_rig_dc_magnetostatic(
    experiment: ExperimentConfig,
    topology: RigConstructiveTopology,
    materials: MaterialLibrary,
    mesh_config: RigGmshConfig,
    output_dir: Path,
    *,
    executables: ExecutableSet | None = None,
    axis_samples: int = 101,
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
    metrics = _axis_metrics(y_m, b_y_t)
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
        "mesh_gate": mesh_run.gate.model_dump(mode="json"),
        "metrics": metrics,
        "scientific_boundary": (
            "Ordinary 3D DC magnetostatics only. Conductivity-driven eddy currents, thermal "
            "effects, anomalies and Portal Hypothesis terms are absent."
        ),
    }
    (output_dir / "metrics.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    return RigMagnetostaticResult(
        y_m=y_m,
        b_y_t=b_y_t,
        mesh_run=mesh_run,
        pro_path=pro_path,
        source_ampere_turns=(source_a.ampere_turns, source_b.ampere_turns),
        solver_versions=version_map,
        metrics=metrics,
    )
