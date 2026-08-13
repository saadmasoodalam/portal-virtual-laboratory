# Unit PVL-1E — Time-Harmonic Eddy-Current Diffusion Benchmark

## Objective

Validate PVL's first conductive-material, frequency-domain electromagnetic solve against an exact magnetic-diffusion solution before inserting conductive iron, copper, water, or saline domains into the validated dual-coil geometry.

PVL-1E remains entirely inside established magneto-quasistatic electromagnetics.

## Benchmark geometry

PVL-POC-004 is a finite uniform conducting slab with a deliberately exact one-dimensional solution:

- slab penetration length: 0.012 m;
- model height: 0.004 m;
- conductivity: 5.8×10^7 S/m;
- relative permeability: 1;
- frequency: 1000 Hz;
- driven boundary: `A_z(0) = 1×10^-4 T·m`;
- grounded boundary: `A_z(L) = 0`;
- harmonic convention: `exp(+iωt)`;
- magnetic solution order: 2;
- convergence mesh sizes: 0.001, 0.0005 and 0.00025 m.

The retained conductivity is copper-like and is used as a numerical benchmark, not yet as a Portal Rig material assignment.

## Exact analytical oracle

For uniform linear material,

`curl(ν curl A) + σ ∂A/∂t = 0`

reduces to

`A'' = k² A`

with

`k² = i ω μ σ`

and

`k = (1+i)/δ`,

where the skin depth is

`δ = sqrt(2 / (ω μ σ))`.

For the retained finite slab,

`A(x) = A0 sinh(k(L-x)) / sinh(kL)`.

PVL independently derives

`B_y = -dA/dx`

and

`J_z = -i ω σ A`.

The time-averaged Joule power density for peak-valued phasors is

`q_avg = 0.5 σ ω² |A|²`.

For the retained 1 kHz conductivity benchmark, the analytical skin depth is approximately **0.00208981 m**, or **2.08981 mm**.

## GetDP formulation

The numerical model uses a complex frequency-domain vector-potential formulation with:

- magnetic reluctivity `ν = 1/(μ0 μr)`;
- conductor conductivity `σ`;
- `DtDof` conductivity term;
- `Type Complex; Frequency Freq`;
- hierarchical second-order magnetic approximation;
- first-order geometric elements;
- complex A, B and induced J extraction along the slab centreline.

A validation run exposed a post-processing parser error: in a complex GetDP system, even an explicitly real quantity written with `Format Table` retains a final real/imaginary scalar pair. PVL initially read the residual imaginary column and therefore produced false zeros. The parser was corrected to consume the actual requested real-value column, and a regression test now fixes that table layout permanently.

No physical discrepancy was normalized away.

## CI convergence evidence

GitHub Actions used Gmsh 4.12.1 and GetDP 3.2.0.

### Mesh sequence

- h = 0.001 m: 80 nodes / 158 elements;
- h = 0.0005 m: 265 nodes / 528 elements;
- h = 0.00025 m: 969 nodes / 1,936 elements.

The final two meshes changed the sampled complex vector potential by only approximately **0.00552%** of its peak magnitude.

### Finest-mesh error

Against the exact finite-slab analytical oracle:

- A maximum peak-normalized complex error: **0.01200%**;
- A RMS peak-normalized complex error: **0.00591%**;
- B maximum peak-normalized complex error: **0.14435%**;
- B RMS peak-normalized complex error: **0.06035%**;
- J maximum peak-normalized complex error: **0.01200%**;
- J RMS peak-normalized complex error: **0.00591%**.

All retained POC-004 acceptance criteria passed.

## Representative field values

At the driven surface, x = 0:

- FEM `A_z = 1.00000×10^-4 + i0 T·m`, exactly matching the imposed boundary;
- FEM `B_y ≈ 0.0479173 + i0.0477810 T`;
- analytical `B_y ≈ 0.0478509 + i0.0478526 T`;
- FEM `J_z ≈ -i3.6442475×10^7 A/m²`, matching the analytical value at the retained precision.

At x = 0.004 m, approximately 1.91 skin depths into the conductor:

- FEM `A_z ≈ -4.94962×10^-6 - i1.38914×10^-5 T·m`;
- analytical `A_z ≈ -4.95656×10^-6 - i1.38889×10^-5 T·m`;
- FEM `J_z ≈ -5.06237×10^6 + i1.80376×10^6 A/m²`;
- analytical `J_z ≈ -5.06147×10^6 + i1.80629×10^6 A/m²`.

The expected amplitude decay and phase lag into the conductor are reproduced quantitatively.

## Automated acceptance gate

`pvl poc004-eddy` returns non-zero unless all criteria pass:

- at least 3 mesh levels;
- strictly decreasing characteristic mesh sizes;
- strictly increasing node and element counts;
- finest A maximum complex error below 1%;
- finest A RMS complex error below 0.5%;
- finest B maximum complex error below 3%;
- finest J maximum complex error below 1%;
- final successive A change below 0.2%.

The retained CI evidence passes every criterion by a substantial margin.

## Scientific meaning

PVL now has a validated numerical baseline for:

- finite electrical conductivity;
- magnetic diffusion;
- skin depth;
- complex field phase lag;
- induced current density;
- frequency-domain conductor response;
- Joule-heating source density derived from the harmonic current response.

This is the first PVL layer in which frequency has a material consequence rather than being only a source-waveform convention.

The result does **not** demonstrate anomalous physics, spacetime coupling, or a portal. It validates the ordinary conductive electromagnetic response that must be subtracted from later Rig simulations.

## Command

```bash
pvl poc004-eddy --output results/poc004_eddy
```

Optional parameters include frequency, conductivity, relative permeability, solution order and convergence mesh sizes.

## Unit status

PVL-1E / POC-004: **validated in CI**.

The recommended next controlled expansion is to place a finite conductive body into the already validated independent dual-coil geometry and confirm superposition, shielding, phase lag, induced current and Joule-loss behavior while retaining POC-001 through POC-004 as permanent regression gates.
