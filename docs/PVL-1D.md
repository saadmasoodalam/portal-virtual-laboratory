# Unit PVL-1D — Phase and Signed-Frequency Baseline

## Objective

Establish the ordinary-physics meaning of phase and signed angular frequency for the validated coaxial dual-coil system before introducing conductive materials, eddy currents, Joule heating, or any Portal Hypothesis terms.

PVL must distinguish three separate controls:

1. static coil polarity/sign;
2. sinusoidal phase;
3. the sign convention used for angular frequency, +ω or -ω.

For the retained coaxial air-only geometry, both coils generate collinear axial magnetic fields. A change of the sign of ω therefore does not, by itself, create a distinct rotating magnetic field.

## Implemented in this unit

- independent harmonic drive configuration for coil A and coil B;
- common frequency magnitude with explicit per-coil `omega_sign`;
- arbitrary phase for each coil;
- canonical positive-frequency complex phasor representation;
- direct signed-frequency real-cosine evaluation;
- one-cycle time-domain reconstruction;
- same-phase addition test;
- π-phase cancellation test;
- π/2 quadrature-resultant test;
- zero-phase +ω/-ω equivalence test;
- signed-frequency/phase equivalence test;
- global frequency-sign reversal/conjugacy test;
- global frequency-sign reversal magnitude-invariance test;
- phasor-vs-direct time-domain equivalence test;
- explicit automated POC-003 validation gate;
- CI evidence artifact.

## Harmonic convention

For one real sinusoidal current,

`I(t) = A cos(s ω t + φ)`

with `s = +1` or `-1`, the same real waveform can be represented using the positive-frequency convention with phase

`φ+ = s φ`.

PVL therefore stores the sign of ω explicitly but maps it to a canonical positive-frequency phasor as

`I~ = A exp(i s φ)`.

This avoids silently treating a frequency-sign convention as a new physical state.

## Retained POC-003 configuration

- coil A radius: 0.05 m;
- coil A turns: 100;
- coil A current amplitude: 1 A;
- coil A centre: z = -0.025 m;
- coil B radius: 0.05 m;
- coil B turns: 100;
- coil B current amplitude: 1 A;
- coil B centre: z = +0.025 m;
- winding section: 0.002 m × 0.002 m;
- frequency magnitude: 100 Hz;
- baseline phase: 0 rad for both coils;
- baseline omega sign: +1 for both coils;
- samples per cycle: 128;
- probe positions: -0.10, -0.05, -0.025, 0, +0.025, +0.05, +0.10 m.

The spatial field amplitudes use the finite-winding analytical model validated against FEM in PVL-1B and PVL-1C.

## Baseline field

At zero relative phase, the two finite winding-section fields add coherently. The retained analytical peak amplitudes are:

- z = ±0.100 m: approximately 0.0002788741 T;
- z = ±0.050 m: approximately 0.0011136468 T;
- z = ±0.025 m: approximately 0.0017008563 T;
- z = 0: approximately 0.0017983047 T.

## Validation evidence

GitHub Actions executed the POC-003 gate after the already validated POC-001 and POC-002 regressions. All POC-003 criteria passed.

Observed numerical residuals:

- same-phase centre addition relative error: `0.0`;
- π-phase centre-cancellation residual: approximately `1.22465×10^-16` of the single-coil centre scale;
- quadrature centre-magnitude relative error: `0.0`;
- zero-phase single-coil ω-sign reversal difference: `0.0`;
- +ω phase φ versus -ω phase -φ equivalence difference: `0.0`;
- global ω-sign reversal versus complex conjugation difference: `0.0`;
- global ω-sign reversal magnitude difference: `0.0`;
- phasor-versus-direct signed-ω time-domain difference: approximately `2.73387×10^-16` of the peak waveform.

The retained gate tolerances are:

- algebraic identities: `1×10^-10`;
- cancellation: `1×10^-10`;
- phasor/time-domain agreement: `1×10^-12`.

## Scientific interpretation

The result establishes the following baseline facts for the current geometry:

- relative phase changes the real time-dependent superposition of the two coil fields;
- 0 phase produces coherent addition;
- π phase produces the expected opposed field and exact mid-plane cancellation for the symmetric pair;
- π/2 phase produces the expected quadrature resultant;
- changing only the sign of ω at zero phase does not create a new scalar magnetic waveform;
- at non-zero phase, signed frequency is equivalent to the corresponding conjugate phase representation;
- reversing the sign of ω globally conjugates the phasor while preserving field magnitude.

Therefore **+ω/-ω must not yet be interpreted as opposite physical magnetic rotation in this coaxial scalar-field model**.

A genuinely rotating magnetic field requires at least two spatially non-collinear magnetic-field components with a controlled phase relationship, or another directional degree of freedom. The present two coils are coaxial, so their field vectors remain collinear even when their temporal phases differ.

## Scope boundary

PVL-1D does not model:

- conductor conductivity;
- eddy currents;
- skin depth;
- induced current phase lag;
- Joule heating;
- iron or copper bulk material response;
- water/saline dielectric or conductive response;
- temperature coupling;
- Portal Hypothesis terms.

Those effects can make frequency physically consequential rather than merely a source-waveform convention and belong to the next controlled layer.

## Command

```bash
pvl poc003-phase --output results/poc003_phase
```

The command writes `poc003_phase_gate.json` and returns non-zero if any retained identity fails.

## Unit status

PVL-1D / POC-003: **validated in CI** for the retained phase and signed-frequency baseline.

The recommended next controlled expansion is a time-harmonic conductive-material benchmark for eddy currents and complex field response. The validated POC-001, POC-002 and POC-003 cases should remain permanent regression gates while that layer is introduced.
