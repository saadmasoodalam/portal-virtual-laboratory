from __future__ import annotations

from pathlib import Path

from pvl.core.models import POC002Config


def render_magnetostatic_pro(config: POC002Config) -> str:
    """Render the established-physics two-source axisymmetric GetDP problem."""
    s = config.source_section
    order = config.mesh.order
    ja = -(config.coil_a.turns * config.coil_a.signed_current_a) / s.area_m2
    jb = -(config.coil_b.turns * config.coil_b.signed_current_a) / s.area_m2
    y_min = min(config.probe_z_m)
    y_max = max(config.probe_z_m)

    edge_basis = ""
    edge_constraint = ""
    edge_constraint_definition = ""
    integration_points = 4
    if order == 2:
        edge_basis = """
      { Name se2; NameOfCoef ae2; Function BF_PerpendicularEdge_2E;
        Support Dom_Hcurl_a_Mag_2D; Entity EdgesOf[All]; }"""
        edge_constraint = """
      { NameOfCoef ae2; EntityType EdgesOf; NameOfConstraint a0_Mag_2D; }"""
        edge_constraint_definition = """
  { Name a0_Mag_2D;
    Case {
      { Region Boundary; Value 0.; }
    }
  }"""
        integration_points = 6

    return f'''// PVL-POC-002 dual-coil GetDP magnetostatic model.
// Established physics only: linear magnetostatic superposition.
// Axisymmetric convention: model lies in z=0 plane, rotation axis is y.
// Magnetic finite-element solution order: {order}.

Group {{
  Air = Region[1];
  CoilA = Region[2];
  CoilB = Region[3];
  Boundary = Region[10];
  Axis = Region[11];

  Vol_Mag = Region[{{Air, CoilA, CoilB}}];
  Vol_S_Mag = Region[{{CoilA, CoilB}}];
  Dom_Hcurl_a_Mag_2D = Region[{{Vol_Mag}}];
}}

Function {{
  mu0 = 4.e-7 * Pi;
  nu[Region[{{Air, CoilA, CoilB}}]] = 1. / mu0;
  // Independently signed homogenized winding current densities.
  js[CoilA] = Vector[0., 0., {ja:.17g}];
  js[CoilB] = Vector[0., 0., {jb:.17g}];
}}

Constraint {{
  {{ Name a_Mag_2D;
    Case {{
      {{ Region Boundary; Value 0.; }}
    }}
  }}
{edge_constraint_definition}
}}

FunctionSpace {{
  {{ Name Hcurl_a_Mag_2D; Type Form1P;
    BasisFunction {{
      {{ Name se; NameOfCoef ae; Function BF_PerpendicularEdge;
        Support Dom_Hcurl_a_Mag_2D; Entity NodesOf[All]; }}{edge_basis}
    }}
    Constraint {{
      {{ NameOfCoef ae; EntityType NodesOf; NameOfConstraint a_Mag_2D; }}{edge_constraint}
    }}
  }}
}}

Jacobian {{
  {{ Name Vol;
    Case {{
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
  {{ Name Magnetostatics_a_2D; Type FemEquation;
    Quantity {{
      {{ Name a; Type Local; NameOfSpace Hcurl_a_Mag_2D; }}
    }}
    Equation {{
      Galerkin {{ [ nu[] * Dof{{d a}}, {{d a}} ];
        In Vol_Mag; Jacobian Vol; Integration Int; }}
      Galerkin {{ [ -js[], {{a}} ];
        In Vol_S_Mag; Jacobian Vol; Integration Int; }}
    }}
  }}
}}

Resolution {{
  {{ Name Mag;
    System {{
      {{ Name Sys_Mag; NameOfFormulation Magnetostatics_a_2D; }}
    }}
    Operation {{
      Generate[Sys_Mag]; Solve[Sys_Mag]; SaveSolution[Sys_Mag];
    }}
  }}
}}

PostProcessing {{
  {{ Name Mag; NameOfFormulation Magnetostatics_a_2D;
    Quantity {{
      {{ Name b;
        Value {{ Local {{ [ {{d a}} ]; In Vol_Mag; Jacobian Vol; }} }}
      }}
    }}
  }}
}}

PostOperation {{
  {{ Name Axis; NameOfPostProcessing Mag;
    Operation {{
      Print[b,
        OnLine{{{{{config.probe_radial_offset_m:.17g}, {y_min:.17g}, 0.}}
               {{{config.probe_radial_offset_m:.17g}, {y_max:.17g}, 0.}}}}{{{config.probe_samples}}},
        Format Table, File "b_axis.txt"];
    }}
  }}
}}
'''


def write_magnetostatic_pro(config: POC002Config, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_magnetostatic_pro(config), encoding="utf-8")
    return path
