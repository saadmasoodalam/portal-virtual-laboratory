export interface ScientificRunSummary {
  experiment_id: string;
  package_id: string;
  run_id: string;
  job_id: string;
  solver_route: string;
  solver_execution: boolean;
  geometry_fidelity: string;
  mesh_configuration_hash: string;
  created_utc: string;
  checksum_verified: true;
  hypothesis_analysis: boolean;
  physical_validation: boolean;
  relative_path: string;
}

export interface ScientificRunCatalog {
  experiment_id: string;
  runs: ScientificRunSummary[];
}

export interface ScientificRunDetail {
  summary: ScientificRunSummary;
  metrics: Record<string, number>;
  solver_metadata: Record<string, unknown>;
  experiment_metadata: Record<string, unknown>;
}

const configuredBase = (import.meta.env.VITE_PVL_API_BASE_URL ?? '').trim();
const apiBase = configuredBase.endsWith('/') ? configuredBase.slice(0, -1) : configuredBase;

function endpoint(path: string): string {
  return `${apiBase}${path}`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function requiredString(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  if (typeof value !== 'string' || !value) throw new Error(`Result API field ${key} must be a non-empty string.`);
  return value;
}

function requiredBoolean(record: Record<string, unknown>, key: string): boolean {
  const value = record[key];
  if (typeof value !== 'boolean') throw new Error(`Result API field ${key} must be boolean.`);
  return value;
}

function parseSummary(value: unknown): ScientificRunSummary {
  if (!isRecord(value)) throw new Error('Result run summary must be an object.');
  if (value.checksum_verified !== true) throw new Error('Result API returned an unverified scientific run.');
  const hypothesis = requiredBoolean(value, 'hypothesis_analysis');
  const physicalValidation = requiredBoolean(value, 'physical_validation');
  if (hypothesis) throw new Error('Established-physics result catalog must not report hypothesis analysis as active.');
  return {
    experiment_id: requiredString(value, 'experiment_id'),
    package_id: requiredString(value, 'package_id'),
    run_id: requiredString(value, 'run_id'),
    job_id: requiredString(value, 'job_id'),
    solver_route: requiredString(value, 'solver_route'),
    solver_execution: requiredBoolean(value, 'solver_execution'),
    geometry_fidelity: requiredString(value, 'geometry_fidelity'),
    mesh_configuration_hash: requiredString(value, 'mesh_configuration_hash'),
    created_utc: requiredString(value, 'created_utc'),
    checksum_verified: true,
    hypothesis_analysis: false,
    physical_validation: physicalValidation,
    relative_path: requiredString(value, 'relative_path'),
  };
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    throw new Error(`Results API returned non-JSON content (HTTP ${response.status}).`);
  }
}

function rejected(status: number, payload: unknown): Error {
  if (isRecord(payload) && isRecord(payload.detail) && typeof payload.detail.message === 'string') {
    return new Error(`Results API rejected the request (HTTP ${status}): ${payload.detail.message}`);
  }
  return new Error(`Results API rejected the request (HTTP ${status}).`);
}

export async function fetchScientificRunCatalog(experimentId: string, signal?: AbortSignal): Promise<ScientificRunCatalog> {
  const id = experimentId.trim();
  if (!id) throw new Error('Experiment ID is required.');
  const response = await fetch(endpoint(`/api/v1/results/${encodeURIComponent(id)}`), { signal });
  const payload = await readJson(response);
  if (!response.ok) throw rejected(response.status, payload);
  if (!isRecord(payload) || !Array.isArray(payload.runs)) throw new Error('Results catalog response is malformed.');
  return {
    experiment_id: requiredString(payload, 'experiment_id'),
    runs: payload.runs.map(parseSummary),
  };
}

export async function fetchScientificRunDetail(summary: ScientificRunSummary, signal?: AbortSignal): Promise<ScientificRunDetail> {
  const response = await fetch(
    endpoint(`/api/v1/results/${encodeURIComponent(summary.experiment_id)}/${encodeURIComponent(summary.package_id)}/${encodeURIComponent(summary.run_id)}/${encodeURIComponent(summary.job_id)}`),
    { signal },
  );
  const payload = await readJson(response);
  if (!response.ok) throw rejected(response.status, payload);
  if (!isRecord(payload) || !isRecord(payload.metrics) || !isRecord(payload.solver_metadata) || !isRecord(payload.experiment_metadata)) {
    throw new Error('Scientific result detail response is malformed.');
  }
  const metrics: Record<string, number> = {};
  for (const [key, value] of Object.entries(payload.metrics)) {
    if (typeof value === 'number' && Number.isFinite(value)) metrics[key] = value;
  }
  return {
    summary: parseSummary(payload.summary),
    metrics,
    solver_metadata: { ...payload.solver_metadata },
    experiment_metadata: { ...payload.experiment_metadata },
  };
}
