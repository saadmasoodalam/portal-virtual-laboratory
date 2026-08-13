from pvl.geometry.rig_manifest import GeometryComponent, RigGeometryManifest, RigShape
from pvl.rig.schema import RigV1Schema


def _m(value, path: str) -> float:
    if value.value_m is None:
        raise ValueError(f"missing geometry value: {path}")
    return float(value.value_m)


def _position(value, path: str) -> tuple[float, float, float]:
    return (_m(value.x, path + ".x"), _m(value.y, path + ".y"), _m(value.z, path + ".z"))


def _axis(value) -> tuple[float, float, float]:
    length = (value.x * value.x + value.y * value.y + value.z * value.z) ** 0.5
    return (value.x / length, value.y / length, value.z / length)


def compile_rig_geometry(rig: RigV1Schema) -> RigGeometryManifest:
    readiness = rig.readiness_report()
    if not readiness.computational_ready:
        raise ValueError("Rig geometry contains unknown required measurements")

    frame = rig.frame
    boundary = rig.copper_boundary
    chamber = rig.sample_chamber
    outer_radius = _m(chamber.outer_radius, "sample_chamber.outer_radius")
    wall = _m(chamber.wall_thickness, "sample_chamber.wall_thickness")
    if wall >= outer_radius:
        raise ValueError("sample chamber wall must be smaller than its outer radius")

    components = [
        GeometryComponent(
            component_id="steel_frame",
            shape=RigShape.FRAME_ENVELOPE,
            material_id=frame.material_id,
            center_m=(0.0, 0.0, 0.0),
            parameters_m={
                "outer_width": _m(frame.outer_width, "frame.outer_width"),
                "outer_depth": _m(frame.outer_depth, "frame.outer_depth"),
                "outer_height": _m(frame.outer_height, "frame.outer_height"),
                "member_width": _m(frame.member_width, "frame.member_width"),
                "member_thickness": _m(frame.member_thickness, "frame.member_thickness"),
            },
        ),
        GeometryComponent(
            component_id="copper_boundary",
            shape=RigShape.OPEN_RECTANGULAR_LOOP,
            material_id=boundary.material_id,
            center_m=(0.0, 0.0, 0.0),
            parameters_m={
                "outer_width": _m(boundary.outer_width, "copper_boundary.outer_width"),
                "outer_depth": _m(boundary.outer_depth, "copper_boundary.outer_depth"),
                "strip_width": _m(boundary.strip_width, "copper_boundary.strip_width"),
                "thickness": _m(boundary.thickness, "copper_boundary.thickness"),
                "gap_width": _m(boundary.gap_width, "copper_boundary.gap_width"),
            },
            metadata={
                "baseline_open_loop": boundary.baseline_open_loop,
                "electrically_isolated_from_frame": boundary.electrically_isolated_from_frame,
            },
        ),
    ]

    center = _position(chamber.center, "sample_chamber.center")
    height = _m(chamber.fill_height, "sample_chamber.fill_height")
    components += [
        GeometryComponent(
            component_id="sample_chamber_wall",
            shape=RigShape.CYLINDRICAL_SHELL,
            material_id=chamber.wall_material_id,
            center_m=center,
            axis=(0.0, 0.0, 1.0),
            parameters_m={"outer_radius": outer_radius, "wall_thickness": wall, "height": height},
        ),
        GeometryComponent(
            component_id="sample_medium",
            shape=RigShape.CYLINDRICAL_VOLUME,
            material_id=chamber.medium_material_id,
            center_m=center,
            axis=(0.0, 0.0, 1.0),
            parameters_m={"radius": outer_radius - wall, "height": height},
        ),
    ]

    for name, coil in (("coil_a", rig.coil_a), ("coil_b", rig.coil_b)):
        if coil.turns.value is None:
            raise ValueError(f"missing geometry value: {name}.turns")
        components.append(GeometryComponent(
            component_id=name,
            shape=RigShape.WINDING_ENVELOPE,
            material_id=coil.conductor_material_id,
            center_m=_position(coil.center, name + ".center"),
            axis=_axis(coil.axis),
            parameters_m={
                "mean_radius": _m(coil.mean_radius, name + ".mean_radius"),
                "axial_length": _m(coil.axial_length, name + ".axial_length"),
                "radial_thickness": _m(coil.radial_thickness, name + ".radial_thickness"),
            },
            integer_parameters={"turns": int(coil.turns.value)},
        ))

    for sensor in rig.sensors:
        components.append(GeometryComponent(
            component_id="sensor:" + sensor.sensor_id,
            shape=RigShape.SENSOR_POINT,
            material_id=None,
            center_m=_position(sensor.position, "sensor:" + sensor.sensor_id),
            axis=_axis(sensor.axis) if sensor.axis else None,
            parameters_m={},
            metadata={"sensor_kind": sensor.kind.value},
        ))

    return RigGeometryManifest(rig_id=rig.rig_id, components=tuple(components))
