from __future__ import annotations

from hashlib import sha256
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    def canonical_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))

    def configuration_hash(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


class CoilConfig(FrozenModel):
    radius_m: float = Field(gt=0)
    turns: int = Field(gt=0)
    current_a: float
    center_z_m: float = 0.0
    polarity: Literal[-1, 1] = 1

    @property
    def signed_current_a(self) -> float:
        return self.current_a * self.polarity


class CoilSourceSectionConfig(FrozenModel):
    """Finite rectangular source section used to approximate a filamentary loop in FEM."""

    radial_thickness_m: float = Field(default=0.002, gt=0)
    axial_height_m: float = Field(default=0.002, gt=0)

    @property
    def area_m2(self) -> float:
        return self.radial_thickness_m * self.axial_height_m


class AirDomainConfig(FrozenModel):
    radius_m: float = Field(default=0.30, gt=0)
    half_height_m: float = Field(default=0.30, gt=0)
    fem_extent_multiplier: float = Field(default=2.0, ge=1.0)

    @property
    def fem_radius_m(self) -> float:
        return self.radius_m * self.fem_extent_multiplier

    @property
    def fem_half_height_m(self) -> float:
        return self.half_height_m * self.fem_extent_multiplier


class MeshConfig(FrozenModel):
    characteristic_length_m: float = Field(default=0.02, gt=0)
    order: Literal[1, 2] = 1


class POC001Config(FrozenModel):
    name: str = "PVL-POC-001"
    coil: CoilConfig = CoilConfig(radius_m=0.05, turns=100, current_a=1.0)
    source_section: CoilSourceSectionConfig = CoilSourceSectionConfig()
    air: AirDomainConfig = AirDomainConfig()
    mesh: MeshConfig = MeshConfig()
    probe_z_m: tuple[float, ...] = (-0.10, -0.05, 0.0, 0.05, 0.10)
    probe_radial_offset_m: float = Field(default=1.0e-5, gt=0)
    probe_samples: int = Field(default=241, ge=21)

    @model_validator(mode="after")
    def validate_domain_contains_coil(self) -> "POC001Config":
        half_radial = self.source_section.radial_thickness_m / 2
        half_axial = self.source_section.axial_height_m / 2
        if self.coil.radius_m - half_radial <= 0:
            raise ValueError("coil source section must remain away from the symmetry axis")
        if self.air.radius_m <= self.coil.radius_m + half_radial:
            raise ValueError("air domain radius must contain the complete coil source section")
        if self.air.half_height_m <= abs(self.coil.center_z_m) + half_axial:
            raise ValueError("air domain must contain the complete coil source section")
        if self.probe_radial_offset_m >= self.coil.radius_m - half_radial:
            raise ValueError("probe radial offset must lie inside the coil axis region")
        if any(abs(z) >= self.air.half_height_m for z in self.probe_z_m):
            raise ValueError("all probes must lie strictly inside the nominal air domain")
        return self
