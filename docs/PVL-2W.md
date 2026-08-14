# PVL-2W — Trusted Scientific Results Dashboard

Status: stacked implementation candidate on PVL-2V

## Objective

PVL-2W closes the first user-visible loop from an immutable scientific execution to the browser. The browser can discover checksum-verified persisted runs and inspect normalized numerical metrics without reading arbitrary filesystem paths and without confusing numerical execution with physical validation or Portal-hypothesis interpretation.

## Trusted result catalog

The backend scans only the PVL scientific-run layout:

`results/<experiment_id>/executions/<package_id>/<run_id>/scientific/<job_id>/`

A run enters the trusted catalog only when:

- `job_manifest.json` validates against the scientific-run schema;
- `checksums.json` exists;
- every checksummed file still matches its SHA-256 digest;
- the signed run/package/job identities match the requested path.

Corrupt or incomplete records are excluded from catalog listings. Addressing one directly returns an integrity error instead of displaying untrusted metrics.

## API

Catalog:

`GET /api/v1/results/<experiment_id>`

Detail:

`GET /api/v1/results/<experiment_id>/<package_id>/<run_id>/<job_id>`

Detail responses include normalized scalar metrics plus solver and experiment metadata. Raw field files remain preserved in the scientific result directory and are not converted into browser truth by this unit.

## Browser dashboard

The laboratory adds a **Scientific results** view with:

- experiment-ID lookup;
- checksum-verified run list;
- run/job identity;
- solver route and solver-execution flag;
- geometry fidelity and mesh hash;
- explicit physical-validation status;
- explicit hypothesis-analysis status;
- normalized numerical metrics.

The TypeScript client rejects a result marked as hypothesis analysis inside this established-physics catalog.

## Scientific boundary

A solver-executed result is not automatically physically validated. PVL-2W displays these states independently and does not produce a Portal classification.

No result is accepted because it looks interesting. Integrity and provenance are prerequisites for display.

## Next visualization stage

PVL-2W intentionally starts with trusted scalar evidence. Full field visualization should consume preserved scientific field exports (VTU/XDMF or a verified downsampled derivative), with the raw full-resolution file retained for ParaView/debugging.
