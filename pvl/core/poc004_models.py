from __future__ import annotations

from pydantic import Field, model_validator

from pvl.core.models import FrozenModel, MeshConfig


class POC004Config(FrozenModel):
    """Finite conducting-slab benchmark for time-harmonic magnetic diffusion.

    The slab is intentionally simple enough to have an exact 1D complex analytical solution.
    It validates GetDP's magneto-quasistatic conductivity term before conductive materials are
    inserted into the dual-coil PVL geometry.
    """

    name: str = "PVL-POC-004"
    length_m: float = Field(default=0.012, gt=0)
    height_m: float = Field(default=0.004, gt=0)
    conductivity_s_m: float = Field(default=5.8e7, gt=0)
    relative_permeability: float = Field(default=1.0, gt=0)
    frequency_hz: float = Field(default=1000.0, gt=0)
    boundary_vector_potential_t_m: float = Field(default=1.0e-4, gt=0)
    mesh: MeshConfig = MeshConfig(characteristic_length_m=0.001, order=2)
    probe_x_m: tuple[float, ...] = (0.0, 0.002, 0.004, 0.006, 0.008, 0.010)
    line_samples: int = Field(default=121, ge=21)

    @model_validator(mode="after")
    def validate_probe_locations(self) -> "POC004Config":
        if any(x < 0.0 or x >= self.length_m for x in self.probe_x_m):
            raise ValueError("POC-004 probes must satisfy 0 <= x < slab length")
        if tuple(sorted(self.probe_x_m)) != self.probe_x_m:
            raise ValueError("POC-004 probes must be sorted in ascending x")
        return self
