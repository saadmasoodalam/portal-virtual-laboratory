from __future__ import annotations

import math

from pydantic import Field, model_validator

from pvl.core.models import (
    AirDomainConfig,
    CoilConfig,
    CoilSourceSectionConfig,
    FrozenModel,
    HarmonicDriveConfig,
    MeshConfig,
)
from pvl.core.physics import MU0


class ConductiveInsertConfig(FrozenModel):
    """Axisymmetric annular conductor retained for the POC-005 integration benchmark."""

    inner_radius_m: float = Field(default=0.012, ge=0)
    outer_radius_m: float = Field(default=0.038, gt=0)
    axial_thickness_m: float = Field(default=0.006, gt=0)
    center_z_m: float = 0.0
    conductivity_s_m: float = Field(default=5.8e7, ge=0)
    relative_permeability: float = Field(default=1.0, gt=0)

    @model_validator(mode="after")
    def validate_radii(self) -> "ConductiveInsertConfig":
        if self.outer_radius_m <= self.inner_radius_m:
            raise ValueError("conductive insert outer radius must exceed inner radius")
        return self


class POC005Config(FrozenModel):
    """Time-harmonic dual-coil system with a finite conductive annular insert.

    The geometry is deliberately simpler than the Portal Boundary Physics Rig. Its purpose is
    to validate ordinary shielding, induced-current phase lag, Joule loss, source superposition
    and mesh convergence after POC-001 through POC-004 have validated the component solvers.
    """

    name: str = "PVL-POC-005"
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
    drive_a: HarmonicDriveConfig = HarmonicDriveConfig(frequency_hz=1000.0)
    drive_b: HarmonicDriveConfig = HarmonicDriveConfig(frequency_hz=1000.0)
    source_section: CoilSourceSectionConfig = CoilSourceSectionConfig()
    insert: ConductiveInsertConfig = ConductiveInsertConfig()
    air: AirDomainConfig = AirDomainConfig()
    mesh: MeshConfig = MeshConfig(characteristic_length_m=0.006, order=2)
    axis_probe_z_m: tuple[float, ...] = (-0.10, -0.05, -0.025, 0.0, 0.025, 0.05, 0.10)
    axis_probe_radial_offset_m: float = Field(default=1.0e-5, gt=0)
    axis_line_samples: int = Field(default=321, ge=31)
    conductor_line_samples: int = Field(default=121, ge=21)

    @property
    def frequency_hz(self) -> float:
        return self.drive_a.frequency_hz

    @property
    def insert_skin_depth_m(self) -> float:
        if self.insert.conductivity_s_m == 0:
            return math.inf
        omega = 2.0 * math.pi * self.frequency_hz
        mu = MU0 * self.insert.relative_permeability
        return math.sqrt(2.0 / (omega * mu * self.insert.conductivity_s_m))

    @model_validator(mode="after")
    def validate_geometry_and_drives(self) -> "POC005Config":
        if not math.isclose(
            self.drive_a.frequency_hz,
            self.drive_b.frequency_hz,
            rel_tol=1e-12,
            abs_tol=0.0,
        ):
            raise ValueError("POC-005 requires equal frequency magnitudes for both coil drives")

        half_source_r = self.source_section.radial_thickness_m / 2.0
        half_source_z = self.source_section.axial_height_m / 2.0
        for label, coil in (("coil A", self.coil_a), ("coil B", self.coil_b)):
            if coil.radius_m - half_source_r <= 0:
                raise ValueError(f"{label} source section must remain away from the axis")
            if coil.radius_m + half_source_r >= self.air.radius_m:
                raise ValueError(f"{label} source section must remain inside the air domain")
            if abs(coil.center_z_m) + half_source_z >= self.air.half_height_m:
                raise ValueError(f"{label} source section must remain inside the air domain")

        insert_half_z = self.insert.axial_thickness_m / 2.0
        if self.insert.outer_radius_m >= self.air.radius_m:
            raise ValueError("conductive insert must remain inside the air domain")
        if abs(self.insert.center_z_m) + insert_half_z >= self.air.half_height_m:
            raise ValueError("conductive insert must remain inside the air domain")

        # The retained integration benchmark keeps the insert separate from both source coils.
        for label, coil in (("coil A", self.coil_a), ("coil B", self.coil_b)):
            radial_overlap = (
                self.insert.inner_radius_m < coil.radius_m + half_source_r
                and self.insert.outer_radius_m > coil.radius_m - half_source_r
            )
            axial_overlap = (
                self.insert.center_z_m - insert_half_z < coil.center_z_m + half_source_z
                and self.insert.center_z_m + insert_half_z > coil.center_z_m - half_source_z
            )
            if radial_overlap and axial_overlap:
                raise ValueError(f"conductive insert must not overlap {label}")

        if self.axis_probe_radial_offset_m >= min(self.coil_a.radius_m, self.coil_b.radius_m):
            raise ValueError("axis probe radial offset must lie inside both coil radii")
        if any(abs(z) >= self.air.half_height_m for z in self.axis_probe_z_m):
            raise ValueError("axis probes must lie inside the nominal air domain")
        return self
