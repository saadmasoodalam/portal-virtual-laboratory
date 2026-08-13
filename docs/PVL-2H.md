# PVL-2H — Frontend Preview API Integration

Status: implementation candidate

## Objective

Connect the React Rig viewer to the validated PVL-2G FastAPI preview boundary while retaining the PVL-2F local preview JSON path as a diagnostic fallback.

## Browser flow

The viewer now accepts either of two JSON document types through the same load control:

1. A `RigV1Schema` manifest is sent to `POST /api/v1/rig/preview`.
2. A document already labeled `fidelity = illustrative_geometry` is parsed locally as the diagnostic fallback.

The API client validates the returned scene again with the existing browser `parsePreviewScene` guard before rendering it.

## Scientific boundary

PVL-2H still does not expose Gmsh, GetDP, simulation execution, FEM result data, or the Portal Hypothesis Analyzer. The browser renders only preview geometry with `solver_mesh = false`.

The local fallback does not upgrade provenance or fidelity. It exists only for inspecting a previously exported preview scene when the API is unavailable or when a saved scene needs debugging.

## API client

`frontend/src/api.ts` provides the narrow browser client for:

- `GET /api/v1/health` boundary verification.
- `POST /api/v1/rig/preview` Rig preview requests.
- runtime parsing of readiness and material-library provenance.
- readable HTTP 422 readiness failures.
- optional `VITE_PVL_API_BASE_URL` support for deployment.

For local development, Vite proxies `/api` to `http://127.0.0.1:8000`, allowing the frontend to run separately from FastAPI without adding a broad CORS policy.

## Viewer behavior

The scene panel identifies whether the displayed geometry came from the validated preview API or from a local diagnostic preview file. Existing component visibility, selection, inspection, orbit/pan/zoom, and fidelity guards are unchanged.

## Test gate

PVL-2H must pass:

- frontend TypeScript typecheck.
- frontend production build.
- existing Python/API tests.
- POC-001 through POC-005 FEM regression validation.

No established-physics solver equations or acceptance thresholds are changed by this unit.

## Next unit

PVL-2I should introduce a controlled Rig-manifest editor form backed by the existing measurement/status schema, without enabling solver execution. The editor should preserve measurement provenance and should not silently convert illustrative values into measured hardware data.
