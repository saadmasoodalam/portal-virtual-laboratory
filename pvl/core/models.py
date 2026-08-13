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


class AirDomainConfig(FrozenModel):
    radius_m: float = Field(default=0.30, gt=0)
    half_height_m: float = Field(default=0.30, gt=0)


class MeshConfig(FrozenModel):
    characteristic_length_m: float = Field(default=0.02, gt=0)
    order: Literal[1, 2] = 1


class POC001Config(FrozenModel):
    name: str = "PVL-POC-001"
    coil: CoilConfig = CoilConfig(radius_m=0.05, turns=100, current_a=1.0)
    air: AirDomainConfig = AirDomainConfig()
    mesh: MeshConfig = MeshConfig()
    probe_z_m: tuple[float, ...] = (-0.10, -0.05, 0.0, 0.05, 0.10)

    @model_validator(mode="after")
    def validate_domain_contains_coil(self) -> "POC001Config":
        if self.air.radius_m <= self.coil.radius_m:
            raise ValueError("air domain radius must exceed coil radius")
        if self.air.half_height_m <= abs(self.coil.center_z_m):
            raise ValueError("air domain must contain coil center")
        return self
