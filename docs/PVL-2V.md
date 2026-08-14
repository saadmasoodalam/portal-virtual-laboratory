# PVL-2V — Complete-Rig Magneto-Thermal Conduction

Status: stacked implementation candidate on PVL-2U

## Objective

PVL-2V adds the first complete-Rig thermal field calculation downstream of the harmonic electromagnetic solution. The model transfers time-averaged passive-conductor Joule heat into a steady thermal-conduction solve.

## Thermal model

The thermal field solves

`-div(k grad T) = Q_J`

with

`Q_J = 0.5 sigma |E|^2`

for the harmonic phasor convention used by PVL-2U.

Material thermal conductivity is taken explicitly from the versioned PVL material library for every physical volume.

## Environmental approximation

PVL-2V does **not** silently invent a convection coefficient. The surrounding air domain is retained as a thermal-conduction medium and the remote outer-air boundary is clamped to the chosen ambient temperature (default 293.15 K).

This is an exploratory conduction-only environment model. It intentionally omits:

- natural convection;
- forced airflow;
- radiation;
- evaporation/phase change;
- temperature-dependent electrical conductivity;
- thermal expansion and mechanical coupling.

Those effects require dedicated later validation rather than hidden empirical terms.

## Coupling

The magnetic and thermal systems are solved sequentially inside one GetDP problem definition:

1. complex harmonic MQ system;
2. steady real thermal system using the already-solved magnetic phasor;
3. temperature field post-processing.

The thermal heat source is the same established-physics phasor Joule expression used for PVL-2U loss diagnostics.

## Outputs

The runner preserves:

- Gmsh geometry and mesh evidence;
- combined GetDP input;
- solver stdout/stderr;
- temperature axis samples;
- fixed temperature probe samples;
- full temperature `.pos` field;
- integrated Joule input;
- normalized thermal metrics and solver versions.

Initial metrics include ambient temperature, axis minimum/maximum/center temperature, temperature rise and integrated Joule input.

## Safety/scientific boundary

This is a numerical low-energy heat-transfer model. It contains no biological response model, no portal term, no anomaly classifier, no high-temperature material transformation and no claim that a computed temperature rise is a spacetime effect.

## Validation path

Before release the stage must pass:

- real Gmsh/GetDP magneto-thermal CI smoke;
- non-negative Joule input;
- finite temperature field;
- no temperature below the fixed ambient boundary for the positive-source steady problem beyond numerical tolerance;
- thermal mesh sensitivity checks;
- an energy-balance gate once boundary heat-flux integration is added;
- independent thermal benchmark against an analytical/simple conduction problem.

PVL-2V remains exploratory until those gates pass.
