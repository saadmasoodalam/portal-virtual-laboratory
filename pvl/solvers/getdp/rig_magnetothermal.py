from __future__ import annotations

from math import isfinite
from pathlib import Path

from pvl.experiments.models import ExperimentConfig
from pvl.geometry.constructive import RigConstructiveTopology
from pvl.geometry.gmsh_rig import RigGmshManifest
from pvl.materials.library import MaterialLibrary
from pvl.solvers.getdp.rig_magnetoquasistatic import (
    build_rig_magnetoquasistatic_model,
    render_rig_magnetoquasistatic_pro,
)
from pvl.solvers.getdp.rig_magnetostatic import _region_name


def render_rig_magnetothermal_pro(
    experiment: ExperimentConfig,
    topology: RigConstructiveTopology,
    manifest: RigGmshManifest,
    materials: MaterialLibrary,
    *,
    ambient_temperature_k: float = 293.15,
    axis_samples: int = 101,
    probe_y_m: tuple[float, ...] = (),
) -> str:
    """Extend the complete-Rig MQ model with steady conduction driven by Joule heat.

    The thermal model intentionally begins with a conduction-only environmental approximation:
    every physical volume, including the surrounding-air domain, is assigned its explicit material
    thermal conductivity and the remote outer-air boundary is clamped to the ambient temperature.
    Natural/forced convection is therefore not inferred or hidden inside an empirical coefficient.
    A later CFD/convection unit may replace this approximation after it receives its own validation.
    """
    if not isfinite(ambient_temperature_k) or ambient_temperature_k <= 0.0:
        raise ValueError("ambient thermal boundary temperature must be finite and positive")
    model = build_rig_magnetoquasistatic_model(experiment, topology, manifest, materials)
    base = render_rig_magnetoquasistatic_pro(
        experiment,
        topology,
        manifest,
        materials,
        axis_samples=axis_samples,
        probe_y_m=probe_y_m,
    )

    all_volume_tags = [manifest.air_physical_tag] + [region.physical_tag for region in manifest.physical_regions]
    conductor_tags = [region.physical_tag for region in model.conductors]
    air = materials.require("air_baseline")
    air_k = air.properties.thermal_conductivity_w_m_k
    if air_k is None or air_k <= 0.0:
        raise ValueError("air material lacks positive thermal conductivity")

    k_lines = [f"  k_The[Region[{manifest.air_physical_tag}]] = {air_k:.17g};"]
    for region in manifest.physical_regions:
        if region.material_id is None:
            raise ValueError(f"thermal material region has no material id: {region.primitive_id}")
        record = materials.require(region.material_id)
        conductivity = record.properties.thermal_conductivity_w_m_k
        if conductivity is None or conductivity <= 0.0:
            raise ValueError(f"material lacks positive thermal conductivity: {region.material_id}")
        k_lines.append(f"  k_The[{_region_name(region.primitive_id)}] = {conductivity:.17g};")

    _, _, ymin, ymax, _, _ = manifest.air_bounds_m
    chamber = next(item for item in topology.primitives if item.primitive_id == "sample:medium")
    px, _, pz = chamber.center_m
    margin = max(1e-6, 0.01 * (ymax - ymin))
    y0 = ymin + margin
    y1 = ymax - margin

    probe_lines: list[str] = []
    for index, y_value in enumerate(probe_y_m):
        if not isfinite(y_value) or not (ymin < y_value < ymax):
            raise ValueError("thermal point probe must be finite and inside the air-domain Y bounds")
        probe_lines.append(
            f'      Print[T_The_Post, OnPoint {{{px:.17g}, {y_value:.17g}, {pz:.17g}}}, Format Table, File "temperature_probe_{index:03d}.txt"];'
        )
    probe_block = "\n".join(probe_lines)
    if probe_block:
        probe_block += "\n"

    thermal = f'''

// -----------------------------------------------------------------------------
// PVL-2V steady thermal extension.
// Joule heat is transferred from the already-solved complex MQ phasor field.
// Surrounding air is represented by conduction only and the distant external air
// boundary is clamped to T_ambient. No unvalidated convection coefficient is hidden.
// -----------------------------------------------------------------------------
Group {{
  Vol_The = Region[{{{', '.join(str(tag) for tag in all_volume_tags)}}}];
  Vol_Q_The = Region[{{{', '.join(str(tag) for tag in conductor_tags)}}}];
  Bnd_The = Region[{manifest.outer_boundary_physical_tag}];
}}

Function {{
  T_ambient = {ambient_temperature_k:.17g};
{chr(10).join(k_lines)}
}}

Constraint {{
  {{ Name T_The;
    Case {{
      {{ Region Bnd_The; Value T_ambient; }}
    }}
  }}
}}

FunctionSpace {{
  {{ Name H1_T_The; Type Form0;
    BasisFunction {{
      {{ Name sn; NameOfCoef Tn; Function BF_Node;
        Support Vol_The; Entity NodesOf[All]; }}
    }}
    Constraint {{
      {{ NameOfCoef Tn; EntityType NodesOf; NameOfConstraint T_The; }}
    }}
  }}
}}

Formulation {{
  {{ Name Thermal_Joule_3D; Type FemEquation;
    Quantity {{
      {{ Name T; Type Local; NameOfSpace H1_T_The; }}
      {{ Name a; Type Local; NameOfSpace Hcurl_a_MQ; }}
    }}
    Equation {{
      Integral {{ [ k_The[] * Dof{{d T}}, {{d T}} ];
        In Vol_The; Jacobian Vol; Integration Int; }}
      Integral {{ [ -0.5 * sigma[] * <a>[SquNorm[Dt[{{a}}]]], {{T}} ];
        In Vol_Q_The; Jacobian Vol; Integration Int; }}
    }}
  }}
}}

Resolution {{
  {{ Name MagThe;
    System {{
      {{ Name Sys_MagThe_MQ; NameOfFormulation Magnetoquasistatics_a_3D;
        Type Complex; Frequency Freq; }}
      {{ Name Sys_MagThe_The; NameOfFormulation Thermal_Joule_3D; }}
    }}
    Operation {{
      Generate[Sys_MagThe_MQ]; Solve[Sys_MagThe_MQ]; SaveSolution[Sys_MagThe_MQ];
      Generate[Sys_MagThe_The]; Solve[Sys_MagThe_The]; SaveSolution[Sys_MagThe_The];
    }}
  }}
}}

PostProcessing {{
  {{ Name The; NameOfFormulation Thermal_Joule_3D;
    Quantity {{
      {{ Name T_The_Post;
        Value {{ Term {{ [ {{T}} ]; In Vol_The; Jacobian Vol; }} }}
      }}
      {{ Name Q_Joule_The;
        Value {{
          Integral {{ [ 0.5 * sigma[] * <a>[SquNorm[Dt[{{a}}]]] ];
            In Vol_Q_The; Jacobian Vol; Integration Int; }}
        }}
      }}
    }}
  }}
}}

PostOperation {{
  {{ Name ThermalDiagnostics; NameOfPostProcessing The;
    Operation {{
      Print[T_The_Post, OnLine{{{{{px:.17g}, {y0:.17g}, {pz:.17g}}}{{{px:.17g}, {y1:.17g}, {pz:.17g}}}}}{{{axis_samples}}},
        Format Table, File "temperature_axis.txt"];
{probe_block}      Print[T_The_Post, OnElementsOf Vol_The, File "temperature.pos"];
      Print[Q_Joule_The[Vol_Q_The], OnGlobal, Format Table, File "thermal_joule_input.txt"];
    }}
  }}
}}
'''
    return base + thermal


def write_rig_magnetothermal_pro(
    experiment: ExperimentConfig,
    topology: RigConstructiveTopology,
    manifest: RigGmshManifest,
    materials: MaterialLibrary,
    path: Path,
    *,
    ambient_temperature_k: float = 293.15,
    axis_samples: int = 101,
    probe_y_m: tuple[float, ...] = (),
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        render_rig_magnetothermal_pro(
            experiment,
            topology,
            manifest,
            materials,
            ambient_temperature_k=ambient_temperature_k,
            axis_samples=axis_samples,
            probe_y_m=probe_y_m,
        ),
        encoding="utf-8",
    )
    return path
