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


def _validate_coil_inside_domain(
    coil: CoilConfig,
    source_section: CoilSourceSectionConfig,
    air: AirDomainConfig,
    *,
    label: str,
) -> None:
    half_radial = source_section.radial_thickness_m / 2
    half_axial = source_section.axial_height_m / 2
    if coil.radius_m - half_radial <= 0:
        raise ValueError(f"{label} source section must remain away from the symmetry axis")
    if air.radius_m <= coil.radius_m + half_radial:
        raise ValueError(f"air domain radius must contain the complete {label} source section")
    if air.half_height_m <= abs(coil.center_z_m) + half_axial:
        raise ValueError(f"air domain must contain the complete {label} source section")


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
        _validate_coil_inside_domain(self.coil, self.source_section, self.air, label="coil")
        half_radial = self.source_section.radial_thickness_m / 2
        if self.probe_radial_offset_m >= self.coil.radius_m - half_radial:
            raise ValueError("probe radial offset must lie inside the coil axis region")
        if any(abs(z) >= self.air.half_height_m for z in self.probe_z_m):
            raise ValueError("all probes must lie strictly inside the nominal air domain")
        return self


class POC002Config(FrozenModel):
    """Two independently driven coaxial coils for the established-physics baseline."""

    name: str = "PVL-POC-002"
    coil_a: CoilConfig = CoilConfig(
        radius_m=0.05,
        turns=100,
        current_a=1.0,
        center_z_m=-0.025,
        polarity=1,
    )
    coil_b: CoilConfig = CoilConfig(
        radius_m=0.05,
        turns=100,
        current_a=1.0,
        center_z_m=0.025,
        polarity=1,
    )
    source_section: CoilSourceSectionConfig = CoilSourceSectionConfig()
    air: AirDomainConfig = AirDomainConfig()
    mesh: MeshConfig = MeshConfig()
    probe_z_m: tuple[float, ...] = (-0.10, -0.05, -0.025, 0.0, 0.025, 0.05, 0.10)
    probe_radial_offset_m: float = Field(default=1.0e-5, gt=0)
    probe_samples: int = Field(default=321, ge=31)

    @model_validator(mode="after")
    def validate_dual_coil_geometry(self) -> "POC002Config":
        _validate_coil_inside_domain(self.coil_a, self.source_section, self.air, label="coil A")
        _validate_coil_inside_domain(self.coil_b, self.source_section, self.air, label="coil B")

        half_radial = self.source_section.radial_thickness_m / 2
        minimum_inner_radius = min(self.coil_a.radius_m, self.coil_b.radius_m) - half_radial
        if self.probe_radial_offset_m >= minimum_inner_radius:
            raise ValueError("probe radial offset must lie inside both coil radii")
        if any(abs(z) >= self.air.half_height_m for z in self.probe_z_m):
            raise ValueError("all probes must lie strictly inside the nominal air domain")

        radial_overlap = (
            abs(self.coil_a.radius_m - self.coil_b.radius_m)
            < self.source_section.radial_thickness_m
        )
        axial_overlap = (
            abs(self.coil_a.center_z_m - self.coil_b.center_z_m)
            < self.source_section.axial_height_m
        )
        if radial_overlap and axial_overlap:
            raise ValueError("coil A and coil B source sections must not overlap")
        return self
