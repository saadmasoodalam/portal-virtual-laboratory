from __future__ import annotations

from pathlib import Path

from pvl.core.poc005_models import POC005Config


def render_magnetoquasistatic_pro(config: POC005Config) -> str:
    """Render the POC-005 time-harmonic dual-source conductive-insert problem.

    The formulation is linear magneto-quasistatics only. Coil phases are represented with
    GetDP's frequency-domain ``F_Cos_wt_p`` phasor function. The sign of omega has already been
    mapped to the equivalent canonical positive-frequency phase by ``HarmonicDriveConfig``, as
    validated independently in POC-003.
    """
    s = config.source_section
    order = config.mesh.order
    ja = -(config.coil_a.turns * config.coil_a.signed_current_a) / s.area_m2
    jb = -(config.coil_b.turns * config.coil_b.signed_current_a) / s.area_m2
    phase_a = config.drive_a.canonical_positive_frequency_phase_rad
    phase_b = config.drive_b.canonical_positive_frequency_phase_rad
    y_min = min(config.axis_probe_z_m)
    y_max = max(config.axis_probe_z_m)
    insert = config.insert

    # Do not use the conductor mid-plane as the retained J-convergence probe. For the
    # pi-opposed dual-coil state, A_phi and therefore J_phi are antisymmetric in z and the exact
    # mid-plane is a physical cancellation plane (J=0). Pointwise relative convergence there is
    # consequently ill-conditioned and measures mesh-symmetry residuals rather than conductor
    # response. A fixed quarter-thickness interior plane remains well inside the conductor and
    # carries finite physical induced current in both retained phase states.
    j_probe_z = insert.center_z_m + 0.25 * insert.axial_thickness_m

    edge_basis = ""
    edge_constraint = ""
    edge_constraint_definition = ""
    integration_points = 4
    if order == 2:
        edge_basis = """
      { Name se2; NameOfCoef ae2; Function BF_PerpendicularEdge_2E;
        Support Dom_Hcurl_a_MQ_2D; Entity EdgesOf[All]; }"""
        edge_constraint = """
      { NameOfCoef ae2; EntityType EdgesOf; NameOfConstraint a0_MQ_2D; }"""
        edge_constraint_definition = """
  { Name a0_MQ_2D;
    Case {
      { Region Boundary; Value 0.; }
    }
  }"""
        integration_points = 6

    return f'''// PVL-POC-005: dual-coil harmonic field with conductive annular insert.
// Established magneto-quasistatic electromagnetics only.
// Axisymmetric convention: geometry lies in z=0 plane; rotation axis is y.
// Induced-current convergence is sampled on a fixed interior quarter-thickness plane;
// the exact insert mid-plane is an antisymmetry null for the pi-opposed drive state.

Group {{
  Air = Region[1];
  CoilA = Region[2];
  CoilB = Region[3];
  Insert = Region[4];
  Boundary = Region[10];
  Axis = Region[11];

  Vol_Mag = Region[{{Air, CoilA, CoilB, Insert}}];
  Vol_S_Mag = Region[{{CoilA, CoilB}}];
  Vol_C_Mag = Region[{{Insert}}];
  Dom_Hcurl_a_MQ_2D = Region[{{Vol_Mag}}];
}}

Function {{
  mu0 = 4.e-7 * Pi;
  Freq = {config.frequency_hz:.17g};
  nu[Region[{{Air, CoilA, CoilB}}]] = 1. / mu0;
  nu[Insert] = 1. / (mu0 * {insert.relative_permeability:.17g});
  sigma[Insert] = {insert.conductivity_s_m:.17g};

  // Independent source-current phasors. Static polarity remains separate from phase.
  js[CoilA] = Vector[0., 0., {ja:.17g}] *
    F_Cos_wt_p[]{{2. * Pi * Freq, {phase_a:.17g}}};
  js[CoilB] = Vector[0., 0., {jb:.17g}] *
    F_Cos_wt_p[]{{2. * Pi * Freq, {phase_b:.17g}}};
}}

Constraint {{
  {{ Name a_MQ_2D;
    Case {{
      {{ Region Boundary; Value 0.; }}
    }}
  }}
{edge_constraint_definition}
}}

FunctionSpace {{
  {{ Name Hcurl_a_MQ_2D; Type Form1P;
    BasisFunction {{
      {{ Name se; NameOfCoef ae; Function BF_PerpendicularEdge;
        Support Dom_Hcurl_a_MQ_2D; Entity NodesOf[All]; }}{edge_basis}
    }}
    Constraint {{
      {{ NameOfCoef ae; EntityType NodesOf; NameOfConstraint a_MQ_2D; }}{edge_constraint}
    }}
  }}
}}

Jacobian {{
  {{ Name Vol;
    Case {{
      // Vector-potential axisymmetric formulation validated in POC-001/002.
      {{ Region All; Jacobian VolAxiSqu; }}
    }}
  }}
}}

Integration {{
  {{ Name Int;
    Case {{
      {{ Type Gauss;
        Case {{
          {{ GeoElement Triangle; NumberOfPoints {integration_points}; }}
        }}
      }}
    }}
  }}
}}

Formulation {{
  {{ Name Magnetoquasistatics_a_2D; Type FemEquation;
    Quantity {{
      {{ Name a; Type Local; NameOfSpace Hcurl_a_MQ_2D; }}
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
      {{ Name Sys_MQ; NameOfFormulation Magnetoquasistatics_a_2D;
        Type Complex; Frequency Freq; }}
    }}
    Operation {{
      Generate[Sys_MQ]; Solve[Sys_MQ]; SaveSolution[Sys_MQ];
    }}
  }}
}}

PostProcessing {{
  {{ Name MQ; NameOfFormulation Magnetoquasistatics_a_2D;
    Quantity {{
      {{ Name bYRe;
        Value {{ Term {{ [ Re[CompY[{{d a}}]] ]; In Vol_Mag; Jacobian Vol; }} }}
      }}
      {{ Name bYIm;
        Value {{ Term {{ [ Im[CompY[{{d a}}]] ]; In Vol_Mag; Jacobian Vol; }} }}
      }}
      {{ Name jZRe;
        Value {{ Term {{ [ Re[-sigma[] * CompZ[Dt[{{a}}]]] ]; In Vol_C_Mag; Jacobian Vol; }} }}
      }}
      {{ Name jZIm;
        Value {{ Term {{ [ Im[-sigma[] * CompZ[Dt[{{a}}]]] ]; In Vol_C_Mag; Jacobian Vol; }} }}
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
      Print[bYRe,
        OnLine{{{{{config.axis_probe_radial_offset_m:.17g}, {y_min:.17g}, 0.}}
               {{{config.axis_probe_radial_offset_m:.17g}, {y_max:.17g}, 0.}}}}{{{config.axis_line_samples}}},
        Format Table, File "by_axis_re.txt"];
      Print[bYIm,
        OnLine{{{{{config.axis_probe_radial_offset_m:.17g}, {y_min:.17g}, 0.}}
               {{{config.axis_probe_radial_offset_m:.17g}, {y_max:.17g}, 0.}}}}{{{config.axis_line_samples}}},
        Format Table, File "by_axis_im.txt"];
      Print[jZRe,
        OnLine{{{{{insert.inner_radius_m:.17g}, {j_probe_z:.17g}, 0.}}
               {{{insert.outer_radius_m:.17g}, {j_probe_z:.17g}, 0.}}}}{{{config.conductor_line_samples}}},
        Format Table, File "j_insert_re.txt"];
      Print[jZIm,
        OnLine{{{{{insert.inner_radius_m:.17g}, {j_probe_z:.17g}, 0.}}
               {{{insert.outer_radius_m:.17g}, {j_probe_z:.17g}, 0.}}}}{{{config.conductor_line_samples}}},
        Format Table, File "j_insert_im.txt"];
      Print[JouleLosses[Vol_C_Mag], OnGlobal, Format Table, File "joule_losses.txt"];
    }}
  }}
}}
'''


def write_magnetoquasistatic_pro(config: POC005Config, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_magnetoquasistatic_pro(config), encoding="utf-8")
    return path
