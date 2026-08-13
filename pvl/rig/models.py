"""Compatibility aliases for the canonical PVL Rig v1 schema."""

from pvl.rig.schema import ReadinessReport as RigReadinessReport
from pvl.rig.schema import RigV1Schema as RigV1Definition

__all__ = ["RigReadinessReport", "RigV1Definition"]
