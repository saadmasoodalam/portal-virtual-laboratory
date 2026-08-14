from math import sqrt

from pydantic import BaseModel, ConfigDict

from pvl.geometry.rig_manifest import GeometryComponent, RigGeometryManifest, RigShape


class Bounds3D(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    minimum_m: tuple[float, float, float]
    maximum_m: tuple[float, float, float]

    @property
    def size_m(self) -> tuple[float, float, float]:
        return tuple(b - a for a, b in zip(self.minimum_m, self.maximum_m))


def _centered(center, extents):
    return Bounds3D(
        minimum_m=tuple(c - e for c, e in zip(center, extents)),
        maximum_m=tuple(c + e for c, e in zip(center, extents)),
    )


def component_bounds(component: GeometryComponent) -> Bounds3D:
    p = component.parameters_m
    if component.shape == RigShape.FRAME_ENVELOPE:
        # PVL-2O freezes the legacy schema mapping explicitly:
        # outer_width -> top-view X span, outer_depth -> top-view Y span,
        # outer_height -> declared Z envelope.
        return _centered(component.center_m, (p["outer_width"] / 2, p["outer_depth"] / 2, p["outer_height"] / 2))
    if component.shape == RigShape.OPEN_RECTANGULAR_LOOP:
        return _centered(component.center_m, (p["outer_width"] / 2, p["outer_depth"] / 2, p["thickness"] / 2))
    if component.shape in {RigShape.CYLINDRICAL_SHELL, RigShape.CYLINDRICAL_VOLUME}:
        radius = p.get("outer_radius", p.get("radius"))
        return _centered(component.center_m, (radius, radius, p["height"] / 2))
    if component.shape == RigShape.WINDING_ENVELOPE:
        axis = component.axis
        if axis is None:
            raise ValueError("winding envelope requires an axis")
        radial = p["mean_radius"] + p["radial_thickness"] / 2
        axial = p["axial_length"] / 2
        extents = tuple(axial * abs(a) + radial * sqrt(max(0.0, 1.0 - a * a)) for a in axis)
        return _centered(component.center_m, extents)
    if component.shape == RigShape.SENSOR_POINT:
        return _centered(component.center_m, (0.0, 0.0, 0.0))
    raise ValueError(f"unsupported geometry shape: {component.shape}")


def manifest_bounds(manifest: RigGeometryManifest) -> Bounds3D:
    if not manifest.components:
        raise ValueError("geometry manifest has no components")
    bounds = [component_bounds(component) for component in manifest.components]
    minimum = tuple(min(item.minimum_m[i] for item in bounds) for i in range(3))
    maximum = tuple(max(item.maximum_m[i] for item in bounds) for i in range(3))
    return Bounds3D(minimum_m=minimum, maximum_m=maximum)


def padded_bounds(manifest: RigGeometryManifest, margin_fraction: float = 0.5) -> Bounds3D:
    if margin_fraction <= 0.0:
        raise ValueError("margin_fraction must be positive")
    bounds = manifest_bounds(manifest)
    sizes = bounds.size_m
    pad = tuple(max(size * margin_fraction, 0.01) for size in sizes)
    return Bounds3D(
        minimum_m=tuple(value - pad[i] for i, value in enumerate(bounds.minimum_m)),
        maximum_m=tuple(value + pad[i] for i, value in enumerate(bounds.maximum_m)),
    )
