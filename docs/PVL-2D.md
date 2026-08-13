# PVL-2D — Parametric Rig Geometry Compiler

PVL-2D converts a computationally complete `RigV1Schema` into a deterministic solver-neutral geometry manifest.

The manifest preserves separate components for the frame, open isolated copper boundary, sample-vessel wall, sample medium, both coil winding envelopes, and sensor points. Coil axes are normalized and all geometry is stored in SI metres.

Unknown required measurements block compilation. Illustrative values remain valid only for software and exploratory geometry work; they are not promoted to physical Rig measurements.

The compiler also provides component/world bounds for visualization and future air-domain sizing, JSON import/export for Rig definitions, JSON export for geometry manifests, and a separate provenance record linking Rig-definition and compiled-geometry fingerprints.

This unit deliberately stops before choosing constructive 3D solid topology for the physical frame and copper boundary. That topology must not be guessed from illustrative values. The next geometry adapter can consume the manifest while hardware-fidelity execution remains blocked until measured dimensions are supplied.
