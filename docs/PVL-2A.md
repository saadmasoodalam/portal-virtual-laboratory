# PVL-2A — Material and Measurement Data Layer

Status: validation pending.

This unit adds versioned SI material records, deterministic library hashing, explicit provenance, and a measurement-first digital-twin schema.

Physical measurements are classified as unknown, illustrative, measured, or supplier sourced. Unknown entries cannot hide numeric values. Illustrative values may support exploratory computation but do not qualify as hardware-fidelity data.

The built-in material records are engineering baselines. The steel record is explicitly a linear placeholder with a warning that nonlinear measured or supplier data is required for high-fidelity use.

The canonical `RigV1Schema` intentionally starts with unknown dimensions and reports computational readiness separately from hardware-fidelity readiness. Material-reference fidelity is checked independently.

This unit adds no new physics equation and no hypothesis-layer calculation. Acceptance requires all existing numerical regression gates and the new schema tests to pass in CI.
