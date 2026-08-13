# PVL-2E — Frontend Preview Geometry

PVL-2E adds a browser-facing scene description derived from the deterministic geometry manifest.

Every preview is explicitly labeled `illustrative_geometry` and `solver_mesh=false`. The scene contains component identity, material identity, position, axis, dimensions, integer parameters, metadata, component bounds, world bounds, and the source geometry fingerprint.

The adapter has separate `preview` and `hardware_fidelity` modes. Preview requires computationally complete geometry and valid material references. Hardware-fidelity geometry remains deliberately unavailable until measured/supplier geometry, hardware-fidelity material data, and a validated constructive solid adapter exist.

The preview output is intended for the future React/Three.js interface. It is not a Gmsh mesh and cannot be used as scientific solver evidence.

No FEM equation, material equation, or POC-001 through POC-005 acceptance threshold is changed by this unit.
