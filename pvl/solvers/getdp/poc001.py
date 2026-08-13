from __future__ import annotations

from pathlib import Path

from pvl.core.models import POC001Config


def render_magnetostatic_pro(config: POC001Config) -> str:
    """Render a self-contained GetDP axisymmetric magnetostatic problem.

    The formulation follows GetDP's documented 2D magnetic-vector-potential approach. For
    ``Form1P``/``BF_PerpendicularEdge`` in an axisymmetric model, GetDP's own magnetics
    template uses the second axisymmetric volume Jacobian, ``VolAxiSqu``. This distinction is
    essential: using ``VolAxi`` applies the wrong geometrical scaling to the vector-potential
    formulation and produces a non-physical field amplitude.

    The axisymmetric Jacobian maps the 2D x-y section into the corresponding solid of
    revolution around the y-axis. No Portal Hypothesis terms enter this formulation.
    """
    c = config.coil
    s = config.source_section
    current_density = -(c.turns * c.signed_current_a) / s.area_m2
    y_min = min(config.probe_z_m)
    y_max = max(config.probe_z_m)

    return f'''// PVL-POC-001 GetDP magnetostatic model.
// Established physics only: curl(nu curl a) = js.
// Axisymmetric convention: model lies in z=0 plane, rotation axis is y.
// Form1P axisymmetric magnetics requires the VolAxiSqu Jacobian.

Group {{
  Air = Region[1];
  Coil = Region[2];
  Boundary = Region[10];
  Axis = Region[11];

  Vol_Mag = Region[{{Air, Coil}}];
  Vol_S_Mag = Region[{{Coil}}];
  Dom_Hcurl_a_Mag_2D = Region[{{Vol_Mag}}];
}}

Function {{
  mu0 = 4.e-7 * Pi;
  nu[Region[{{Air, Coil}}]] = 1. / mu0;
  // Homogenized winding current density: J = N I / winding cross-section.
  // Negative z source gives +y axial field for positive signed coil current.
  js[Coil] = Vector[0., 0., {current_density:.17g}];
}}

Constraint {{
  {{ Name a_Mag_2D;
    Case {{
      {{ Region Boundary; Value 0.; }}
    }}
  }}
}}

FunctionSpace {{
  {{ Name Hcurl_a_Mag_2D; Type Form1P;
    BasisFunction {{
      {{ Name se; NameOfCoef ae; Function BF_PerpendicularEdge;
        Support Dom_Hcurl_a_Mag_2D; Entity NodesOf[All]; }}
    }}
    Constraint {{
      {{ NameOfCoef ae; EntityType NodesOf; NameOfConstraint a_Mag_2D; }}
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
          {{ GeoElement Triangle; NumberOfPoints 4; }}
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
      {{ Name a;
        Value {{ Local {{ [ {{a}} ]; In Vol_Mag; Jacobian Vol; }} }}
      }}
      {{ Name b;
        Value {{ Local {{ [ {{d a}} ]; In Vol_Mag; Jacobian Vol; }} }}
      }}
    }}
  }}
}}

PostOperation {{
  {{ Name Map; NameOfPostProcessing Mag;
    Operation {{
      Print[b, OnElementsOf Vol_Mag, File "b.pos"];
    }}
  }}
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


def write_magnetostatic_pro(config: POC001Config, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_magnetostatic_pro(config), encoding="utf-8")
    return path
