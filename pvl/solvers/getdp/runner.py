from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess


class SolverUnavailableError(RuntimeError):
    """Raised when an external FEM executable required by PVL is unavailable."""


class SolverExecutionError(RuntimeError):
    """Raised when Gmsh/GetDP returns a non-zero exit status."""


@dataclass(frozen=True)
class ExecutableSet:
    gmsh: str
    getdp: str


@dataclass(frozen=True)
class SolverVersions:
    gmsh: str
    getdp: str


def discover_executables() -> ExecutableSet:
    gmsh = shutil.which("gmsh")
    getdp = shutil.which("getdp")
    if not gmsh or not getdp:
        missing = [name for name, value in (("gmsh", gmsh), ("getdp", getdp)) if not value]
        raise SolverUnavailableError("Missing required FEM executable(s): " + ", ".join(missing))
    return ExecutableSet(gmsh=gmsh, getdp=getdp)


def run_command(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(args, cwd=cwd, check=True, text=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        command = " ".join(args)
        raise SolverExecutionError(
            f"External solver command failed ({exc.returncode}): {command}\n"
            f"stdout:\n{exc.stdout}\n"
            f"stderr:\n{exc.stderr}"
        ) from exc


def _first_nonempty_line(text: str) -> str:
    for line in text.splitlines():
        value = line.strip()
        if value:
            return value
    return "unknown"


def solver_versions(executables: ExecutableSet | None = None) -> SolverVersions:
    exe = executables or discover_executables()
    gmsh = run_command([exe.gmsh, "-version"], cwd=Path.cwd())
    getdp = run_command([exe.getdp, "-version"], cwd=Path.cwd())
    # Different packaged releases use stdout/stderr differently for version output.
    gmsh_text = (gmsh.stdout + "\n" + gmsh.stderr).strip()
    getdp_text = (getdp.stdout + "\n" + getdp.stderr).strip()
    return SolverVersions(
        gmsh=_first_nonempty_line(gmsh_text),
        getdp=_first_nonempty_line(getdp_text),
    )


def generate_mesh(
    geo_path: Path,
    *,
    dimension: int = 3,
    output_path: Path | None = None,
    executables: ExecutableSet | None = None,
) -> Path:
    """Generate a Gmsh mesh from a .geo file and return the resulting path."""
    if dimension not in (1, 2, 3):
        raise ValueError("dimension must be 1, 2, or 3")
    exe = executables or discover_executables()
    geo_path = geo_path.resolve()
    output_path = (output_path or geo_path.with_suffix(".msh")).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    run_command(
        [exe.gmsh, str(geo_path), f"-{dimension}", "-format", "msh2", "-o", str(output_path)],
        cwd=geo_path.parent,
    )
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise SolverExecutionError(f"Gmsh completed without producing a usable mesh: {output_path}")
    return output_path
