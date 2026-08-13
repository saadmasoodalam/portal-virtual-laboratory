from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess


class SolverUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExecutableSet:
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
    return subprocess.run(args, cwd=cwd, check=True, text=True, capture_output=True)
