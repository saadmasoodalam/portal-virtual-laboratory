from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator


PositiveFloat = Annotated[float, Field(gt=0.0)]
NonNegativeFloat = Annotated[float, Field(ge=0.0)]


class MaterialCategory(StrEnum):
    GAS = "gas"
    METAL = "metal"
    GLASS = "glass"
    LIQUID = "liquid"


class MaterialModelKind(StrEnum):
    NONMAGNETIC = "nonmagnetic"
    LINEAR = "linear"
    LINEAR_PLACEHOLDER = "linear_placeholder"
    NONLINEAR_CURVE = "nonlinear_curve"


class MaterialDataStatus(StrEnum):
    VALIDATED_BENCHMARK = "validated_benchmark"
    ENGINEERING_BASELINE = "engineering_baseline"
    SUPPLIER = "supplier"
    MEASURED = "measured"


class MaterialProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: MaterialDataStatus
    source_label: str = Field(min_length=1)
    notes: str = ""


class MaterialProperties(BaseModel):
    """SI material properties used by PVL's established-physics solvers.

    Optional values are deliberate. A missing property must be handled by the solver adapter rather
    than silently replaced with a guessed value.
    """

    model_config = ConfigDict(extra="forbid")

    electrical_conductivity_s_m: NonNegativeFloat
    relative_permeability: PositiveFloat | None = None
    relative_permittivity: PositiveFloat | None = None
    density_kg_m3: PositiveFloat | None = None
    specific_heat_j_kg_k: PositiveFloat | None = None
    thermal_conductivity_w_m_k: PositiveFloat | None = None
    reference_temperature_k: PositiveFloat = 293.15
    reference_frequency_hz: NonNegativeFloat | None = None


class MaterialDefinition(BaseModel):
    """Versioned material record with explicit fidelity and provenance metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    material_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_\-]*$")
    display_name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    category: MaterialCategory
    model_kind: MaterialModelKind
    properties: MaterialProperties
    provenance: MaterialProvenance
    assumptions: tuple[str, ...] = ()
    fidelity_limitations: tuple[str, ...] = ()
    solver_warning: str = ""

    @model_validator(mode="after")
    def validate_magnetic_model(self) -> "MaterialDefinition":
        if self.model_kind in {
            MaterialModelKind.LINEAR,
            MaterialModelKind.LINEAR_PLACEHOLDER,
            MaterialModelKind.NONMAGNETIC,
        } and self.properties.relative_permeability is None:
            raise ValueError("linear/nonmagnetic material records require relative_permeability")
        if self.model_kind == MaterialModelKind.LINEAR_PLACEHOLDER and not self.solver_warning:
            raise ValueError("linear placeholder materials require an explicit solver_warning")
        return self

    @property
    def is_hardware_fidelity_data(self) -> bool:
        return self.provenance.status in {
            MaterialDataStatus.SUPPLIER,
            MaterialDataStatus.MEASURED,
        }
