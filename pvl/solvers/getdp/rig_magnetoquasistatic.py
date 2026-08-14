from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from pathlib import Path

from pvl.experiments.models import DriveMode, ExperimentConfig
from pvl.geometry.constructive import RigConstructiveTopology
from pvl.geometry.gmsh_rig import RigGmshManifest
from pvl.materials.library import MaterialLibrary
from pvl.solvers.getdp.rig_magnetostatic import (
    HomogenizedWindingSource,
    _region_name,
    _source_expression,
    _winding_source,
)


@dataclass(frozen=True)
class ConductiveRegion:
    primitive_id: str
    physical_tag: int
    material_id: str
    conductivity_s_m: float


@dataclass(frozen=True)
class HarmonicWindingSource:
    spatial: HomogenizedWindingSource
    phase_rad: float


@dataclass(frozen=True)
class RigMagnetoquasistaticModel:
    frequency_hz: float
    source_a: HarmonicWindingSource
    source_b: HarmonicWindingSource
    conductors: tuple[ConductiveRegion, ...]


def build_rig_magnetoquasistatic_model(
    experiment: ExperimentConfig,
    topology: RigConstructiveTopology,
    manifest: RigGmshManifest,
    materials: MaterialLibrary,
) -> RigMagnetoquasistaticModel:
    """Resolve the complete-Rig harmonic source and passive-conductor contract.

    The two winding envelopes are prescribed stranded-current sources and are deliberately excluded
    from the passive conductivity domain. Every other material region with explicit positive
    conductivity participates in eddy-current loss using the versioned material library.
    """
    active = [drive for drive in (experiment.coil_a, experiment.coil_b) if drive.mode != DriveMode.OFF]
    if not active or any(drive.mode != DriveMode.HARMONIC for drive in active):
        raise ValueError("complete-Rig magnetoquasistatics requires harmonic/OFF drives only")
    frequencies = {drive.frequency_hz for drive in active}
    if len(frequencies) != 1 or None in frequencies:
        raise ValueError("complete-Rig magnetoquasistatics requires one common active frequency")
    frequency_hz = float(next(iter(frequencies)))

    source_a = HarmonicWindingSource(
        spatial=_winding_source(
            "winding:coil_a", topology, manifest, experiment.coil_a.signed_current_a
        ),
        phase_rad=experiment.coil_a.canonical_positive_frequency_phase_rad,
    )
    source_b = HarmonicWindingSource(
        spatial=_winding_source(
            "winding:coil_b", topology, manifest, experiment.coil_b.signed_current_a
        ),
        phase_rad=experiment.coil_b.canonical_positive_frequency_phase_rad,
    )

    source_ids = {"winding:coil_a", "winding:coil_b"}
    conductors: list[ConductiveRegion] = []
    for region in manifest.physical_regions:
        if region.primitive_id in source_ids:
            continue
        if region.material_id is None:
            raise ValueError(f"material region has no material id: {region.primitive_id}")
        record = materials.require(region.material_id)
        sigma = record.properties.electrical_conductivity_s_m
        if sigma > 0.0:
            conductors.append(
                ConductiveRegion(
                    primitive_id=region.primitive_id,
                    physical_tag=region.physical_tag,
                    material_id=region.material_id,
                    conductivity_s_m=float(sigma),
                )
            )
    if not conductors:
        raise ValueError("complete-Rig harmonic model has no passive conductive material regions")
    return RigMagnetoquasistaticModel(
        frequency_hz=frequency_hz,
        source_a=source_a,
        source_b=source_b,
        conductors=tuple(conductors),
    )


def _phasor_source_expression(source: HarmonicWindingSource) -> str:
    return (
        f"({_source_expression(source.spatial)}) * "
        f"F_Cos_wt_p[]{{2. * Pi * Freq, {source.phase_rad:.17g}}}"
    )


def render_rig_magnetoquasistatic_pro(
    experiment: ExperimentConfig,
    topology: RigConstructiveTopology,
    manifest: RigGmshManifest,
    materials: MaterialLibrary,
    *,
    axis_samples: int = 101,
    probe_y_m: tuple[float, ...] = (),
) -> str:
    """Render the first complete-Rig 3D frequency-domain eddy-current model.

    This is an established magneto-quasistatic modified-vector-potential formulation. With imposed
    stranded source currents, the electric scalar-potential gradient is absorbed into the modified
    vector-potential gauge, so passive current density is ``j = -sigma * dt(a)``. Voltage-driven
    massive conductors are outside this unit and require the later explicit a-v/circuit formulation.
    """
    if axis_samples < 3:
        raise ValueError("axis_samples must be at least 3")
    if experiment.material_library_fingerprint != materials.fingerprint_sha256():
        raise ValueError("experiment material-library fingerprint does not match loaded library")
    if experiment.rig_definition_fingerprint != topology.source_rig_fingerprint:
        raise ValueError("experiment Rig fingerprint does not match constructive topology")
    if manifest.source_rig_fingerprint != topology.source_rig_fingerprint:
        raise ValueError("Gmsh manifest Rig fingerprint does not match constructive topology")

    model = build_rig_magnetoquasistatic_model(experiment, topology, manifest, materials)
    all_volume_tags = [manifest.air_physical_tag] + [item.physical_tag for item in manifest.physical_regions]
    source_tags = [model.source_a.spatial.physical_tag, model.source_b.spatial.physical_tag]
    conductor_tags = [item.physical_tag for item in model.conductors]

    group_lines = [
        f"  Air = Region[{manifest.air_physical_tag}];",
        f"  Bnd = Region[{manifest.outer_boundary_physical_tag}];",
    ]
    for region in manifest.physical_regions:
        group_lines.append(f"  {_region_name(region.primitive_id)} = Region[{region.physical_tag}];")
    group_lines.extend(
        [
            "  Vol_Mag = Region[{" + ", ".join(str(tag) for tag in all_volume_tags) + "}];",
            "  Vol_S_Mag = Region[{" + ", ".join(str(tag) for tag in source_tags) + "}];",
            "  Vol_C_Mag = Region[{" + ", ".join(str(tag) for tag in conductor_tags) + "}];",
        ]
    )

    material_functions: list[str] = ["  nu[Air] = 1. / mu0;", "  sigma[Air] = 0.;"]
    for region in manifest.physical_regions:
        if region.material_id is None:
            raise ValueError(f"material region has no material id: {region.primitive_id}")
        record = materials.require(region.material_id)
        mur = record.properties.relative_permeability
        if mur is None or mur <= 0.0:
            raise ValueError(f"material lacks positive relative permeability: {region.material_id}")
        sigma = record.properties.electrical_conductivity_s_m
        material_functions.extend(
            [
                f"  nu[{_region_name(region.primitive_id)}] = 1. / (mu0 * ({mur:.17g}));",
                f"  sigma[{_region_name(region.primitive_id)}] = {sigma:.17g};",
            ]
        )

    _, _, ymin, ymax, _, _ = manifest.air_bounds_m
    chamber = next(item for item in topology.primitives if item.primitive_id == "sample:medium")
    px, _, pz = chamber.center_m
    line_margin = max(1e-6, 0.01 * (ymax - ymin))
    line_y0 = ymin + line_margin
    line_y1 = ymax - line_margin

    probe_lines: list[str] = []
    for index, probe_y in enumerate(probe_y_m):
        if not isfinite(probe_y):
            raise ValueError("complete-Rig harmonic point probe coordinate must be finite")
        if not (ymin < probe_y < ymax):
            raise ValueError("complete-Rig harmonic point probe lies outside padded air-domain Y bounds")
        point = f"{{{px:.17g}, {probe_y:.17g}, {pz:.17g}}}"
        probe_lines.extend(
            [
                f'      Print[bYRe, OnPoint {point}, Format Table, File "by_probe_re_{index:03d}.txt"];',
                f'      Print[bYIm, OnPoint {point}, Format Table, File "by_probe_im_{index:03d}.txt"];',
            ]
        )
    probe_block = "\n".join(probe_lines)
    if probe_block:
        probe_block += "\n"

    return f'''// PVL-2U complete-Rig 3D frequency-domain magneto-quasistatic formulation.
// Established electromagnetics only: imposed stranded source currents + passive eddy currents.
// Modified vector potential: E = -dt(a), J = sigma E in passive conductive regions.
// Windings are prescribed current sources and excluded from passive bulk conductivity.
// Harmonic omega sign is mapped only to the canonical positive-frequency source phase.
// No thermal feedback, anomaly classifier, biological model or Portal Hypothesis term is present.

Group {{
{chr(10).join(group_lines)}
}}

Function {{
  mu0 = 4.e-7 * Pi;
  Freq = {model.frequency_hz:.17g};
{chr(10).join(material_functions)}
  js[{_region_name('winding:coil_a')}] = {_phasor_source_expression(model.source_a)};
  js[{_region_name('winding:coil_b')}] = {_phasor_source_expression(model.source_b)};
}}

Constraint {{
  {{ Name a_MQ;
    Case {{
      {{ Region Bnd; Value 0.; }}
    }}
  }}
  {{ Name a_Gauge_MQ;
    Case {{
      {{ Region Vol_Mag; SubRegion Bnd; Value 0.; }}
    }}
  }}
}}

FunctionSpace {{
  {{ Name Hcurl_a_MQ; Type Form1;
    BasisFunction {{
      {{ Name se; NameOfCoef ae; Function BF_Edge;
        Support Vol_Mag; Entity EdgesOf[All]; }}
    }}
    Constraint {{
      {{ NameOfCoef ae; EntityType EdgesOf; NameOfConstraint a_MQ; }}
      {{ NameOfCoef ae; EntityType EdgesOfTreeIn; EntitySubType StartingOn;
        NameOfConstraint a_Gauge_MQ; }}
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
  {{ Name Magnetoquasistatics_a_3D; Type FemEquation;
    Quantity {{
      {{ Name a; Type Local; NameOfSpace Hcurl_a_MQ; }}
    }}
    Equation {{
      Integral {{ [ nu[] * Dof{{d a}}, {{d a}} ];
        In Vol_Mag; Jacobian Vol; Integration Int; }}
      Integral {{ DtDof [ sigma[] * Dof{{a}}, {{a}} ];
        In Vol_C_Mag; Jacobian Vol; Integration Int; }}
      Integral {{ [ -js[], {{a}} ];
        In Vol_S_Mag; Jacobian Vol; Integration Int; }}
    }}
  }}
}}

Resolution {{
  {{ Name MQ;
    System {{
      {{ Name Sys_MQ; NameOfFormulation Magnetoquasistatics_a_3D;
        Type Complex; Frequency Freq; }}
    }}
    Operation {{
      Generate[Sys_MQ]; Solve[Sys_MQ]; SaveSolution[Sys_MQ];
    }}
  }}
}}

PostProcessing {{
  {{ Name MQ; NameOfFormulation Magnetoquasistatics_a_3D;
    Quantity {{
      {{ Name bYRe;
        Value {{ Term {{ [ Re[CompY[{{d a}}]] ]; In Vol_Mag; Jacobian Vol; }} }}
      }}
      {{ Name bYIm;
        Value {{ Term {{ [ Im[CompY[{{d a}}]] ]; In Vol_Mag; Jacobian Vol; }} }}
      }}
      {{ Name jRe;
        Value {{ Term {{ [ Re[-sigma[] * Dt[{{a}}]] ]; In Vol_C_Mag; Jacobian Vol; }} }}
      }}
      {{ Name jIm;
        Value {{ Term {{ [ Im[-sigma[] * Dt[{{a}}]] ]; In Vol_C_Mag; Jacobian Vol; }} }}
      }}
      {{ Name sourceJ;
        Value {{ Term {{ [ js[] ]; In Vol_S_Mag; Jacobian Vol; }} }}
      }}
      {{ Name JouleLosses;
        Value {{
          Integral {{ [ 0.5 * sigma[] * SquNorm[Dt[{{a}}]] ];
            In Vol_C_Mag; Jacobian Vol; Integration Int; }}
        }}
      }}
    }}
  }}
}}

PostOperation {{
  {{ Name Diagnostics; NameOfPostProcessing MQ;
    Operation {{
      Print[bYRe, OnLine{{{{{px:.17g}, {line_y0:.17g}, {pz:.17g}}}{{{px:.17g}, {line_y1:.17g}, {pz:.17g}}}}}{{{axis_samples}}},
        Format Table, File "by_axis_re.txt"];
      Print[bYIm, OnLine{{{{{px:.17g}, {line_y0:.17g}, {pz:.17g}}}{{{px:.17g}, {line_y1:.17g}, {pz:.17g}}}}}{{{axis_samples}}},
        Format Table, File "by_axis_im.txt"];
{probe_block}      Print[jRe, OnElementsOf Vol_C_Mag, File "j_passive_re.pos"];
      Print[jIm, OnElementsOf Vol_C_Mag, File "j_passive_im.pos"];
      Print[sourceJ, OnElementsOf Vol_S_Mag, File "source_j.pos"];
      Print[JouleLosses[Vol_C_Mag], OnGlobal, Format Table, File "joule_losses.txt"];
    }}
  }}
}}
'''


def write_rig_magnetoquasistatic_pro(
    experiment: ExperimentConfig,
    topology: RigConstructiveTopology,
    manifest: RigGmshManifest,
    materials: MaterialLibrary,
    path: Path,
    *,
    axis_samples: int = 101,
    probe_y_m: tuple[float, ...] = (),
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        render_rig_magnetoquasistatic_pro(
            experiment,
            topology,
            manifest,
            materials,
            axis_samples=axis_samples,
            probe_y_m=probe_y_m,
        ),
        encoding="utf-8",
    )
    return path
