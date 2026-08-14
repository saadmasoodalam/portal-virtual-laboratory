from __future__ import annotations

from dataclasses import dataclass
from math import isclose
from pathlib import Path

from pvl.experiments.models import DriveMode, ExperimentConfig
from pvl.geometry.constructive import ConstructivePrimitiveKind, RigConstructiveTopology
from pvl.geometry.gmsh_rig import RigGmshManifest
from pvl.materials.library import MaterialLibrary


@dataclass(frozen=True)
class HomogenizedWindingSource:
    primitive_id: str
    physical_tag: int
    turns: int
    signed_current_a: float
    pack_cross_section_m2: float
    current_density_a_m2: float
    center_m: tuple[float, float, float]
    geometric_axis_y_sign: int
    electrical_reference_y_sign: int = 1

    @property
    def ampere_turns(self) -> float:
        return self.turns * self.signed_current_a

    @property
    def integrated_cross_section_current_a(self) -> float:
        return self.current_density_a_m2 * self.pack_cross_section_m2


def _region_name(primitive_id: str) -> str:
    return "R_" + "".join(character if character.isalnum() else "_" for character in primitive_id)


def _winding_source(
    primitive_id: str,
    topology: RigConstructiveTopology,
    manifest: RigGmshManifest,
    signed_current_a: float,
) -> HomogenizedWindingSource:
    primitive = next((item for item in topology.primitives if item.primitive_id == primitive_id), None)
    if primitive is None or primitive.kind != ConstructivePrimitiveKind.WINDING_ENVELOPE:
        raise ValueError(f"complete-Rig winding primitive is missing: {primitive_id}")
    region = next((item for item in manifest.physical_regions if item.primitive_id == primitive_id), None)
    if region is None:
        raise ValueError(f"Gmsh winding physical region is missing: {primitive_id}")
    if primitive.axis is None:
        raise ValueError(f"winding axis is missing: {primitive_id}")
    if not (
        isclose(primitive.axis[0], 0.0, abs_tol=1e-12)
        and isclose(abs(primitive.axis[1]), 1.0, abs_tol=1e-12)
        and isclose(primitive.axis[2], 0.0, abs_tol=1e-12)
    ):
        raise ValueError(
            "PVL-2Q analytical winding-current source currently requires the frozen ±Y Rig coil axes"
        )
    turns = primitive.integer_parameters.get("turns")
    radial = primitive.parameters_m.get("radial_thickness")
    axial = primitive.parameters_m.get("axial_length")
    if turns is None or turns <= 0 or radial is None or radial <= 0.0 or axial is None or axial <= 0.0:
        raise ValueError(f"invalid winding pack parameters: {primitive_id}")
    area = radial * axial
    ampere_turns = turns * signed_current_a
    return HomogenizedWindingSource(
        primitive_id=primitive_id,
        physical_tag=region.physical_tag,
        turns=turns,
        signed_current_a=signed_current_a,
        pack_cross_section_m2=area,
        current_density_a_m2=ampere_turns / area,
        center_m=primitive.center_m,
        geometric_axis_y_sign=1 if primitive.axis[1] > 0.0 else -1,
    )


def build_winding_sources(
    experiment: ExperimentConfig,
    topology: RigConstructiveTopology,
    manifest: RigGmshManifest,
) -> tuple[HomogenizedWindingSource, HomogenizedWindingSource]:
    """Construct divergence-free azimuthal source amplitudes for the two DC winding packs.

    ``J = N I / A_pack`` and the analytic source flows azimuthally around the frozen Y-axis.
    The geometric normal signs recorded by PVL-2O are deliberately *not* electrical polarity.
    Positive experiment polarity is referenced to global +Y for both coils, matching the validated
    POC-002 convention where equal positive currents add and opposite polarity cancels. The
    integrated current through a radial/axial pack cross-section is exactly ``N I``; turns are not
    applied again in the magnetostatic equation.
    """
    for label, drive in (("coil_a", experiment.coil_a), ("coil_b", experiment.coil_b)):
        if drive.mode not in {DriveMode.OFF, DriveMode.DC}:
            raise ValueError(f"PVL-2Q accepts DC/OFF drives only: {label}={drive.mode.value}")
    return (
        _winding_source("winding:coil_a", topology, manifest, experiment.coil_a.signed_current_a),
        _winding_source("winding:coil_b", topology, manifest, experiment.coil_b.signed_current_a),
    )


def _source_expression(source: HomogenizedWindingSource) -> str:
    cx, _, cz = source.center_m
    radial = f"Sqrt[(X[] - ({cx:.17g}))^2 + (Z[] - ({cz:.17g}))^2]"
    reference = source.electrical_reference_y_sign
    # +Y reference uses +Y × radial_hat. Signed current already contains the experiment polarity.
    return (
        f"({source.current_density_a_m2:.17g}) * Vector["
        f"({reference}) * (Z[] - ({cz:.17g})) / ({radial}), "
        f"0., -({reference}) * (X[] - ({cx:.17g})) / ({radial})]"
    )


def render_rig_magnetostatic_pro(
    experiment: ExperimentConfig,
    topology: RigConstructiveTopology,
    manifest: RigGmshManifest,
    materials: MaterialLibrary,
    *,
    axis_samples: int = 101,
) -> str:
    if axis_samples < 3:
        raise ValueError("axis_samples must be at least 3")
    if experiment.material_library_fingerprint != materials.fingerprint_sha256():
        raise ValueError("experiment material-library fingerprint does not match loaded library")
    if experiment.rig_definition_fingerprint != topology.source_rig_fingerprint:
        raise ValueError("experiment Rig fingerprint does not match constructive topology")
    if manifest.source_rig_fingerprint != topology.source_rig_fingerprint:
        raise ValueError("Gmsh manifest Rig fingerprint does not match constructive topology")

    source_a, source_b = build_winding_sources(experiment, topology, manifest)
    all_volume_tags = [manifest.air_physical_tag] + [item.physical_tag for item in manifest.physical_regions]
    source_tags = [source_a.physical_tag, source_b.physical_tag]

    material_functions: list[str] = ["  nu[Air] = 1. / mu0;"]
    for region in manifest.physical_regions:
        if region.material_id is None:
            raise ValueError(f"material region has no material id: {region.primitive_id}")
        record = materials.require(region.material_id)
        mur = record.properties.relative_permeability
        if mur is None or mur <= 0.0:
            raise ValueError(f"material lacks positive relative permeability: {region.material_id}")
        material_functions.append(
            f"  nu[{_region_name(region.primitive_id)}] = 1. / (mu0 * ({mur:.17g}));"
        )

    group_lines = [
        f"  Air = Region[{manifest.air_physical_tag}];",
        f"  Bnd = Region[{manifest.outer_boundary_physical_tag}];",
    ]
    for region in manifest.physical_regions:
        group_lines.append(f"  {_region_name(region.primitive_id)} = Region[{region.physical_tag}];")
    group_lines.extend([
        "  Vol_Mag = Region[{" + ", ".join(str(tag) for tag in all_volume_tags) + "}];",
        "  Vol_S_Mag = Region[{" + ", ".join(str(tag) for tag in source_tags) + "}];",
    ])

    _, _, ymin, ymax, _, _ = manifest.air_bounds_m
    chamber = next(item for item in topology.primitives if item.primitive_id == "sample:medium")
    px, _, pz = chamber.center_m
    line_margin = max(1e-6, 0.01 * (ymax - ymin))
    line_y0 = ymin + line_margin
    line_y1 = ymax - line_margin

    return f'''// PVL-2Q complete-Rig 3D DC magnetostatic formulation.
// Established magnetostatics only: curl(nu curl a) = js.
// Homogenized winding sources use J = N I / A_pack and analytic divergence-free azimuthal flow.
// Coil geometric normals do not define electrical polarity; +polarity is global +Y for both coils.
// No eddy-current, thermal, anomaly, biological or Portal Hypothesis term is present.

Group {{
{chr(10).join(group_lines)}
}}

Function {{
  mu0 = 4.e-7 * Pi;
{chr(10).join(material_functions)}
  js[{_region_name('winding:coil_a')}] = {_source_expression(source_a)};
  js[{_region_name('winding:coil_b')}] = {_source_expression(source_b)};
}}

Constraint {{
  {{ Name a_Mag;
    Case {{
      {{ Region Bnd; Value 0.; }}
    }}
  }}
  {{ Name a_Gauge_Mag;
    Case {{
      {{ Region Vol_Mag; SubRegion Bnd; Value 0.; }}
    }}
  }}
}}

FunctionSpace {{
  {{ Name Hcurl_a_Mag; Type Form1;
    BasisFunction {{
      {{ Name se; NameOfCoef ae; Function BF_Edge;
        Support Vol_Mag; Entity EdgesOf[All]; }}
    }}
    Constraint {{
      {{ NameOfCoef ae; EntityType EdgesOf; NameOfConstraint a_Mag; }}
      {{ NameOfCoef ae; EntityType EdgesOfTreeIn; EntitySubType StartingOn;
        NameOfConstraint a_Gauge_Mag; }}
    }}
  }}
}}

Jacobian {{
  {{ Name Vol;
    Case {{
      {{ Region All; Jacobian Vol; }}
    }}
  }}
}}

Integration {{
  {{ Name Int;
    Case {{
      {{ Type Gauss;
        Case {{
          {{ GeoElement Tetrahedron; NumberOfPoints 4; }}
        }}
      }}
    }}
  }}
}}

Formulation {{
  {{ Name Magnetostatics_a_3D; Type FemEquation;
    Quantity {{
      {{ Name a; Type Local; NameOfSpace Hcurl_a_Mag; }}
    }}
    Equation {{
      Integral {{ [ nu[] * Dof{{d a}}, {{d a}} ];
        In Vol_Mag; Jacobian Vol; Integration Int; }}
      Integral {{ [ -js[], {{a}} ];
        In Vol_S_Mag; Jacobian Vol; Integration Int; }}
    }}
  }}
}}

Resolution {{
  {{ Name Mag;
    System {{
      {{ Name Sys_Mag; NameOfFormulation Magnetostatics_a_3D; }}
    }}
    Operation {{
      Generate[Sys_Mag]; Solve[Sys_Mag]; SaveSolution[Sys_Mag];
    }}
  }}
}}

PostProcessing {{
  {{ Name Mag; NameOfFormulation Magnetostatics_a_3D;
    Quantity {{
      {{ Name b;
        Value {{
          Term {{ [ {{d a}} ]; In Vol_Mag; Jacobian Vol; }}
        }}
      }}
      {{ Name h;
        Value {{
          Term {{ [ nu[] * {{d a}} ]; In Vol_Mag; Jacobian Vol; }}
        }}
      }}
      {{ Name sourceJ;
        Value {{
          Term {{ [ js[] ]; In Vol_S_Mag; Jacobian Vol; }}
        }}
      }}
    }}
  }}
}}

PostOperation {{
  {{ Name Axis; NameOfPostProcessing Mag;
    Operation {{
      Print[b, OnLine{{{{{px:.17g}, {line_y0:.17g}, {pz:.17g}}}{{{px:.17g}, {line_y1:.17g}, {pz:.17g}}}}}{{{axis_samples}}},
        Format Table, File "b_axis.txt"];
      Print[sourceJ, OnElementsOf Vol_S_Mag, File "source_j.pos"];
    }}
  }}
}}
'''


def write_rig_magnetostatic_pro(
    experiment: ExperimentConfig,
    topology: RigConstructiveTopology,
    manifest: RigGmshManifest,
    materials: MaterialLibrary,
    path: Path,
    *,
    axis_samples: int = 101,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        render_rig_magnetostatic_pro(
            experiment,
            topology,
            manifest,
            materials,
            axis_samples=axis_samples,
        ),
        encoding="utf-8",
    )
    return path
