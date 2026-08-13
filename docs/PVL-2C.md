# PVL-2C — Simulation Preflight

PVL-2C adds the gate between experiment configuration and solver execution.

Preflight verifies the Rig and material fingerprints, required geometry measurements, selected material availability, requested fidelity level, and solver compatibility. Exploratory runs may use explicitly illustrative geometry; hardware-fidelity runs require measured or supplier-sourced inputs.

Solver routing is explicit: inactive controls, DC magnetostatics, and common-frequency harmonic magneto-quasistatics are separate routes. Mixed DC/harmonic states and multiple simultaneous harmonic frequencies are rejected as separate-run requirements.

A simulation job can enter the runnable state only after preflight passes. Job-state transitions are constrained so completed or failed jobs cannot silently restart as the same run identity.

No field equation or numerical acceptance threshold is changed by this unit.
