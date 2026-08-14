from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shutil
import subprocess

from pydantic import Field

from pvl.core.models import FrozenModel
from pvl.geometry.constructive import RigConstructiveTopology
from pvl.geometry.gmsh_rig import RigGmshConfig, RigGmshManifest, write_complete_rig_geo
from pvl.geometry.msh2 import Msh2TetraSummary, parse_msh2_tetra_summary
from pvl.solvers.getdp.runner import SolverExecutionError, run_command


class GmshUnavailableError(RuntimeError):
    pass


class RigMeshGateResult(FrozenModel):
    passed: bool
    criteria: dict[str, bool]
    observed: dict[str, float | int | bool]
    tolerances: dict[str, float | int]


@dataclass(frozen=True)
class RigMeshRun:
    mesh_path: Path
    geo_path: Path
    gmsh_manifest: RigGmshManifest
    summary: Msh2TetraSummary
    gate: RigMeshGateResult
    gmsh_version: str


def discover_gmsh() -> str:
    path = shutil.which("gmsh")
    if not path:
        raise GmshUnavailableError("Missing required geometry executable: gmsh")
    return path


def gmsh_version(executable: str) -> str:
    result = run_command([executable, "-version"], cwd=Path.cwd())
    text = (result.stdout + "\n" + result.stderr).strip()
    return next((line.strip() for line in text.splitlines() if line.strip()), "unknown")


def evaluate_rig_mesh_gate(
    manifest: RigGmshManifest,
    summary: Msh2TetraSummary,
    *,
    minimum_mean_ratio_quality: float = 0.01,
    minimum_tetra_volume_m3: float = 1e-18,
) -> RigMeshGateResult:
    expected_by_tag = {manifest.air_physical_tag: manifest.air_physical_name}
    expected_by_tag.update(
        {region.physical_tag: region.physical_name for region in manifest.physical_regions}
    )
    expected_tags = set(expected_by_tag)
    observed_tags = set(summary.tetrahedra_by_physical_tag)
    expected_names = set(expected_by_tag.values())
    observed_names = set(summary.physical_names.values())
    populated = all(summary.tetrahedra_by_physical_tag.get(tag, 0) > 0 for tag in expected_tags)
    outer_name_ok = summary.surface_physical_names.get(manifest.outer_boundary_physical_tag) == manifest.outer_boundary_physical_name
    outer_triangles = summary.triangles_by_physical_tag.get(manifest.outer_boundary_physical_tag, 0)
    criteria = {
        "has_nodes": summary.node_count > 0,
        "has_tetrahedra": summary.tetrahedron_count > 0,
        "physical_volume_names_exact": observed_names == expected_names,
        "tetra_physical_tags_exact": observed_tags == expected_tags,
        "every_required_volume_populated": populated,
        "all_tetra_volumes_positive": summary.minimum_tetra_volume_m3 > minimum_tetra_volume_m3,
        "minimum_mean_ratio_quality": summary.minimum_mean_ratio_quality >= minimum_mean_ratio_quality,
        "air_region_populated": summary.tetrahedra_by_physical_tag.get(manifest.air_physical_tag, 0) > 0,
        "outer_boundary_physical_name": outer_name_ok,
        "outer_boundary_triangles_populated": outer_triangles > 0,
        "solver_execution_absent": manifest.solver_execution is False,
    }
    observed: dict[str, float | int | bool] = {
        "nodes": summary.node_count,
        "elements": summary.element_count,
        "triangles": summary.triangle_count,
        "tetrahedra": summary.tetrahedron_count,
        "expected_physical_volumes": len(expected_tags),
        "observed_physical_volumes": len(observed_tags),
        "outer_boundary_triangles": outer_triangles,
        "minimum_tetra_volume_m3": summary.minimum_tetra_volume_m3,
        "maximum_tetra_volume_m3": summary.maximum_tetra_volume_m3,
        "minimum_mean_ratio_quality": summary.minimum_mean_ratio_quality,
        "mean_mean_ratio_quality": summary.mean_mean_ratio_quality,
    }
    return RigMeshGateResult(
        passed=all(criteria.values()),
        criteria=criteria,
        observed=observed,
        tolerances={
            "minimum_mean_ratio_quality": minimum_mean_ratio_quality,
            "minimum_tetra_volume_m3": minimum_tetra_volume_m3,
        },
    )


def run_complete_rig_mesh(
    topology: RigConstructiveTopology,
    config: RigGmshConfig,
    output_dir: Path,
    *,
    gmsh_executable: str | None = None,
) -> RigMeshRun:
    """Generate and gate one complete-Rig exploratory mesh without invoking GetDP.

    Gmsh may write an incomplete surface-only ``.msh`` before returning a nonzero exit status.
    PVL therefore captures stdout/stderr even on command failure and never treats mere mesh-file
    existence as proof of a valid three-dimensional mesh.
    """
    gmsh = gmsh_executable or discover_gmsh()
    output_dir.mkdir(parents=True, exist_ok=True)
    geo_path, manifest = write_complete_rig_geo(topology, config, output_dir / "rig_v1.geo")
    mesh_path = (output_dir / "rig_v1.msh").resolve()
    geo_resolved = geo_path.resolve()
    version = gmsh_version(gmsh)

    command = [gmsh, str(geo_resolved), "-3", "-format", "msh2", "-o", str(mesh_path)]
    try:
        mesh_run = run_command(command, cwd=geo_resolved.parent)
    except subprocess.CalledProcessError as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        (output_dir / "gmsh_stdout.log").write_text(stdout, encoding="utf-8")
        (output_dir / "gmsh_stderr.log").write_text(stderr, encoding="utf-8")
        partial = ""
        if mesh_path.is_file():
            partial = f"; partial mesh written ({mesh_path.stat().st_size} bytes)"
        raise SolverExecutionError(
            f"Gmsh complete-Rig 3D meshing failed with exit code {exc.returncode}{partial}"
        ) from exc

    (output_dir / "gmsh_stdout.log").write_text(mesh_run.stdout, encoding="utf-8")
    (output_dir / "gmsh_stderr.log").write_text(mesh_run.stderr, encoding="utf-8")
    if not mesh_path.is_file() or mesh_path.stat().st_size == 0:
        raise SolverExecutionError("Gmsh completed without producing a complete-Rig mesh")

    summary = parse_msh2_tetra_summary(mesh_path)
    gate = evaluate_rig_mesh_gate(manifest, summary)
    if not gate.passed:
        (output_dir / "validation_gate.json").write_text(
            json.dumps(gate.model_dump(mode="json"), indent=2, sort_keys=True), encoding="utf-8"
        )
        raise SolverExecutionError(
            "Gmsh produced a mesh that failed the complete-Rig mesh integrity gate"
        )

    (output_dir / "constructive_topology.json").write_text(
        json.dumps(topology.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (output_dir / "gmsh_manifest.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    metrics = {
        "gmsh_version": version,
        "gmsh_config": config.model_dump(mode="json"),
        "summary": summary.model_dump(mode="json"),
        "tetrahedra_by_physical_name": summary.tetrahedra_by_physical_name,
        "triangles_by_physical_name": summary.triangles_by_physical_name,
        "validation_gate": gate.model_dump(mode="json"),
        "scientific_boundary": (
            "PVL complete-Rig geometry validates CAD/mesh topology and an explicit external "
            "boundary. A GetDP solve is a separate execution gate."
        ),
    }
    (output_dir / "mesh_metrics.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8"
    )
    (output_dir / "validation_gate.json").write_text(
        json.dumps(gate.model_dump(mode="json"), indent=2, sort_keys=True), encoding="utf-8"
    )
    return RigMeshRun(
        mesh_path=mesh_path,
        geo_path=geo_path,
        gmsh_manifest=manifest,
        summary=summary,
        gate=gate,
        gmsh_version=version,
    )
