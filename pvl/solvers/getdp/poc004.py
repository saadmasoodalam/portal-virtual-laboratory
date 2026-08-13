from __future__ import annotations

from pathlib import Path

from pvl.core.poc004_models import POC004Config


def render_magnetoquasistatic_pro(config: POC004Config) -> str:
    """Render the frequency-domain magnetic-diffusion benchmark.

    The formulation follows GetDP's magneto-quasistatic vector-potential tutorial:

        curl(nu curl a) + sigma d(a)/dt = 0

    with a complex frequency-domain system. The left boundary imposes a real A_z phasor and
    the right boundary imposes zero A_z, matching the exact finite-slab analytical oracle.
    """
    order = config.mesh.order
    edge_basis = ""
    edge_constraint = ""
    edge_constraint_definition = ""
    integration_points = 4
    if order == 2:
        edge_basis = """
      { Name se2; NameOfCoef ae2; Function BF_PerpendicularEdge_2E;
        Support Domain; Entity EdgesOf[All]; }"""
        edge_constraint = """
      { NameOfCoef ae2; EntityType EdgesOf; NameOfConstraint a0_MQ_2D; }"""
        edge_constraint_definition = """
  { Name a0_MQ_2D;
    Case {
      { Region Left; Value 0.; }
      { Region Right; Value 0.; }
    }
  }"""
        integration_points = 6

    return f'''// PVL-POC-004 frequency-domain magneto-quasistatic conductor slab.
// Established physics only: curl(nu curl a) + sigma Dt(a) = 0.

Group {{
  Conductor = Region[1];
  Left = Region[10];
  Right = Region[11];
  Domain = Region[{{Conductor}}];
}}

Function {{
  mu0 = 4.e-7 * Pi;
  mur = {config.relative_permeability:.17g};
  nu[Conductor] = 1. / (mu0 * mur);
  sigma[Conductor] = {config.conductivity_s_m:.17g};
  Freq = {config.frequency_hz:.17g};
}}

Constraint {{
  {{ Name a_MQ_2D;
    Case {{
      {{ Region Left; Value {config.boundary_vector_potential_t_m:.17g}; }}
      {{ Region Right; Value 0.; }}
    }}
  }}
{edge_constraint_definition}
}}

FunctionSpace {{
  {{ Name Hcurl_a_MQ_2D; Type Form1P;
    BasisFunction {{
      {{ Name se; NameOfCoef ae; Function BF_PerpendicularEdge;
        Support Domain; Entity NodesOf[All]; }}{edge_basis}
    }}
    Constraint {{
      {{ NameOfCoef ae; EntityType NodesOf; NameOfConstraint a_MQ_2D; }}{edge_constraint}
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
      Integral {{ [ nu[] * Dof{{d a}} , {{d a}} ];
        In Domain; Jacobian Vol; Integration Int; }}
      Integral {{ DtDof [ sigma[] * Dof{{a}} , {{a}} ];
        In Domain; Jacobian Vol; Integration Int; }}
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
      {{ Name aRe;
        Value {{ Local {{ [ Re[CompZ[{{a}}]] ]; In Domain; Jacobian Vol; }} }}
      }}
      {{ Name aIm;
        Value {{ Local {{ [ Im[CompZ[{{a}}]] ]; In Domain; Jacobian Vol; }} }}
      }}
      {{ Name bYRe;
        Value {{ Local {{ [ Re[CompY[{{d a}}]] ]; In Domain; Jacobian Vol; }} }}
      }}
      {{ Name bYIm;
        Value {{ Local {{ [ Im[CompY[{{d a}}]] ]; In Domain; Jacobian Vol; }} }}
      }}
      {{ Name jZRe;
        Value {{ Local {{ [ Re[-sigma[] * CompZ[Dt[{{a}}]]] ]; In Domain; Jacobian Vol; }} }}
      }}
      {{ Name jZIm;
        Value {{ Local {{ [ Im[-sigma[] * CompZ[Dt[{{a}}]]] ]; In Domain; Jacobian Vol; }} }}
      }}
    }}
  }}
}}

PostOperation {{
  {{ Name Line; NameOfPostProcessing MQ;
    Operation {{
      Print[aRe, OnLine{{{{0., 0., 0.}}{{{config.length_m:.17g}, 0., 0.}}}}{{{config.line_samples}}},
        Format Table, File "a_re.txt"];
      Print[aIm, OnLine{{{{0., 0., 0.}}{{{config.length_m:.17g}, 0., 0.}}}}{{{config.line_samples}}},
        Format Table, File "a_im.txt"];
      Print[bYRe, OnLine{{{{0., 0., 0.}}{{{config.length_m:.17g}, 0., 0.}}}}{{{config.line_samples}}},
        Format Table, File "by_re.txt"];
      Print[bYIm, OnLine{{{{0., 0., 0.}}{{{config.length_m:.17g}, 0., 0.}}}}{{{config.line_samples}}},
        Format Table, File "by_im.txt"];
      Print[jZRe, OnLine{{{{0., 0., 0.}}{{{config.length_m:.17g}, 0., 0.}}}}{{{config.line_samples}}},
        Format Table, File "jz_re.txt"];
      Print[jZIm, OnLine{{{{0., 0., 0.}}{{{config.length_m:.17g}, 0., 0.}}}}{{{config.line_samples}}},
        Format Table, File "jz_im.txt"];
    }}
  }}
}}
'''


def write_magnetoquasistatic_pro(config: POC004Config, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_magnetoquasistatic_pro(config), encoding="utf-8")
    return path
