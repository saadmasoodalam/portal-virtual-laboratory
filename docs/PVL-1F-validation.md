# PVL-1F validation record

Status: **PASSED**

GitHub Actions run `31734467275` completed the full regression chain with Gmsh 4.12.1 and GetDP 3.2.0 on Ubuntu 24.04. The Python test suite reported **52 passed**, and POC-001 through POC-005 all passed their machine gates.

## POC-005 retained evidence

- same-phase zero-conductivity analytical field error: 0.00069133943
- opposed-phase zero-conductivity analytical field error: 0.00011673297
- same-phase final B mesh change: 0.00003614144
- opposed-phase final B mesh change: 0.00000792970
- same-phase final J mesh change: 0.00047737710
- opposed-phase final J mesh change: 0.00082594314
- same-phase final Joule-loss mesh change: 0.00000889070
- opposed-phase final Joule-loss mesh change: 0.00001133000
- same-phase final Joule loss: 0.02650938985 W
- opposed-phase final Joule loss: 0.00344158386 W
- B superposition error: 4.212e-16
- J superposition error: 5.346e-16
- finest mesh per retained phase state: 131,322 nodes / 263,731 elements

All retained tolerances passed without relaxation.

## Validation issue and correction

The first complete POC-005 run failed only the opposed-phase pointwise J-convergence check. The raw evidence showed that J had been sampled exactly on the insert center plane. In the symmetric pi-opposed source state that plane is a physical antisymmetry cancellation plane, so the expected signal there is zero and a relative pointwise convergence metric becomes ill-conditioned.

The threshold was not loosened and the result was not rescaled. The retained J sampling line was moved to a fixed interior plane one quarter of the insert thickness from the center (`z = +0.0015 m`). This preserves a finite physical signal in both retained phase states. A regression test now protects this sampling rule.

After the correction, the opposed-phase final J mesh-change metric became 0.00082594314, comfortably below the unchanged 0.01 limit.

## Scientific boundary

This record validates the ordinary magneto-quasistatic coupled dual-coil/conductor baseline only. It contains no Portal Hypothesis term and is not evidence of anomalous or spacetime-coupling behavior.
