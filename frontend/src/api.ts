import { parsePreviewScene } from './parsePreviewScene';
import type { PreviewScene } from './types';

export interface PreviewApiHealth {
  status: 'ok';
  apiVersion: string;
  scope: 'preview_geometry_only';
  solverExecution: false;
}

export interface PreviewReadiness {
  computational_ready: boolean;
  hardware_fidelity_ready: boolean;
  missing_required_measurements: string[];
  non_fidelity_measurements: string[];
}

export interface PreviewProvenance {
  api_version: string;
  material_library_version: string;
  material_library_fingerprint: string;
}

export interface PreviewApiResult {
  readiness: PreviewReadiness;
  provenance: PreviewProvenance;
  scene: PreviewScene;
}

export type MaterialCategory = 'gas' | 'metal' | 'glass' | 'liquid';

export interface MaterialCatalogItem {
  material_id: string;
  display_name: string;
  category: MaterialCategory;
  model_kind: string;
  provenance_status: string;
  hardware_fidelity_data: boolean;
  solver_warning: string;
}

export interface MaterialCatalog {
  library_version: string;
  library_fingerprint: string;
  materials: MaterialCatalogItem[];
}

export type DriveMode = 'off' | 'dc' | 'harmonic';

export interface CoilDriveState {
  mode: DriveMode;
  current_a: number;
  polarity: -1 | 1;
  frequency_hz: number | null;
  phase_rad: number;
  omega_sign: -1 | 1;
}

export interface ExperimentConfig {
  experiment_id: string;
  rig_id: string;
  purpose: 'baseline' | 'calibration' | 'validation' | 'sweep';
  medium: 'air' | 'distilled_water' | 'saline_0p9';
  copper_boundary_state: 'open' | 'closed';
  coil_a: CoilDriveState;
  coil_b: CoilDriveState;
  duration_s: number;
  repetitions: number;
  randomization_seed: number;
  solver_fidelity: 'exploratory' | 'hardware_fidelity';
  material_library_fingerprint: string;
  rig_definition_fingerprint: string;
  biological_testing: false;
  notes: string;
}

export interface ExperimentValidationResult {
  accepted: true;
  physics_state_hash: string;
  solver_execution: false;
  experiment: ExperimentConfig;
}

const configuredBase = (import.meta.env.VITE_PVL_API_BASE_URL ?? '').trim();
const apiBase = configuredBase.endsWith('/') ? configuredBase.slice(0, -1) : configuredBase;

function endpoint(path: string): string {
  return `${apiBase}${path}`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function requireString(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  if (typeof value !== 'string' || value.length === 0) {
    throw new Error(`API response field ${key} must be a non-empty string.`);
  }
  return value;
}

function requireNumber(record: Record<string, unknown>, key: string): number {
  const value = record[key];
  if (typeof value !== 'number' || !Number.isFinite(value)) throw new Error(`API response field ${key} must be a finite number.`);
  return value;
}

function requireBoolean(record: Record<string, unknown>, key: string): boolean {
  const value = record[key];
  if (typeof value !== 'boolean') {
    throw new Error(`API response field ${key} must be boolean.`);
  }
  return value;
}

function requireStringArray(record: Record<string, unknown>, key: string): string[] {
  const value = record[key];
  if (!Array.isArray(value) || value.some((entry) => typeof entry !== 'string')) {
    throw new Error(`API response field ${key} must be a string array.`);
  }
  return [...value];
}

function requireEnum<T extends string>(record: Record<string, unknown>, key: string, allowed: readonly T[]): T {
  const value = requireString(record, key);
  if (!allowed.includes(value as T)) throw new Error(`API response field ${key} contains unsupported value ${value}.`);
  return value as T;
}

function parseReadiness(value: unknown): PreviewReadiness {
  if (!isRecord(value)) throw new Error('Preview API readiness payload must be an object.');
  return {
    computational_ready: requireBoolean(value, 'computational_ready'),
    hardware_fidelity_ready: requireBoolean(value, 'hardware_fidelity_ready'),
    missing_required_measurements: requireStringArray(value, 'missing_required_measurements'),
    non_fidelity_measurements: requireStringArray(value, 'non_fidelity_measurements'),
  };
}

function parseProvenance(value: unknown): PreviewProvenance {
  if (!isRecord(value)) throw new Error('Preview API provenance payload must be an object.');
  return {
    api_version: requireString(value, 'api_version'),
    material_library_version: requireString(value, 'material_library_version'),
    material_library_fingerprint: requireString(value, 'material_library_fingerprint'),
  };
}

function parseApiResult(value: unknown): PreviewApiResult {
  if (!isRecord(value)) throw new Error('Preview API response must be a JSON object.');
  return {
    readiness: parseReadiness(value.readiness),
    provenance: parseProvenance(value.provenance),
    scene: parsePreviewScene(value.scene),
  };
}

function parseMaterialCatalog(value: unknown): MaterialCatalog {
  if (!isRecord(value)) throw new Error('Material catalog response must be an object.');
  const materials = value.materials;
  if (!Array.isArray(materials)) throw new Error('Material catalog materials must be an array.');
  return {
    library_version: requireString(value, 'library_version'),
    library_fingerprint: requireString(value, 'library_fingerprint'),
    materials: materials.map((entry) => {
      if (!isRecord(entry)) throw new Error('Material catalog entry must be an object.');
      const category = requireEnum(entry, 'category', ['gas', 'metal', 'glass', 'liquid'] as const);
      return {
        material_id: requireString(entry, 'material_id'),
        display_name: requireString(entry, 'display_name'),
        category,
        model_kind: requireString(entry, 'model_kind'),
        provenance_status: requireString(entry, 'provenance_status'),
        hardware_fidelity_data: requireBoolean(entry, 'hardware_fidelity_data'),
        solver_warning: typeof entry.solver_warning === 'string' ? entry.solver_warning : '',
      };
    }),
  };
}

function parseCoilDrive(value: unknown): CoilDriveState {
  if (!isRecord(value)) throw new Error('Experiment coil drive must be an object.');
  const polarity = requireNumber(value, 'polarity');
  const omegaSign = requireNumber(value, 'omega_sign');
  const frequency = value.frequency_hz;
  if (frequency !== null && (typeof frequency !== 'number' || !Number.isFinite(frequency))) {
    throw new Error('Experiment frequency_hz must be null or a finite number.');
  }
  if (polarity !== -1 && polarity !== 1) throw new Error('Experiment polarity must be -1 or +1.');
  if (omegaSign !== -1 && omegaSign !== 1) throw new Error('Experiment omega_sign must be -1 or +1.');
  return {
    mode: requireEnum(value, 'mode', ['off', 'dc', 'harmonic'] as const),
    current_a: requireNumber(value, 'current_a'),
    polarity,
    frequency_hz: frequency,
    phase_rad: requireNumber(value, 'phase_rad'),
    omega_sign: omegaSign,
  };
}

function parseExperimentConfig(value: unknown): ExperimentConfig {
  if (!isRecord(value)) throw new Error('Experiment payload must be an object.');
  if (value.biological_testing !== false) throw new Error('Experiment boundary violation: biological_testing must be false.');
  return {
    experiment_id: requireString(value, 'experiment_id'),
    rig_id: requireString(value, 'rig_id'),
    purpose: requireEnum(value, 'purpose', ['baseline', 'calibration', 'validation', 'sweep'] as const),
    medium: requireEnum(value, 'medium', ['air', 'distilled_water', 'saline_0p9'] as const),
    copper_boundary_state: requireEnum(value, 'copper_boundary_state', ['open', 'closed'] as const),
    coil_a: parseCoilDrive(value.coil_a),
    coil_b: parseCoilDrive(value.coil_b),
    duration_s: requireNumber(value, 'duration_s'),
    repetitions: requireNumber(value, 'repetitions'),
    randomization_seed: requireNumber(value, 'randomization_seed'),
    solver_fidelity: requireEnum(value, 'solver_fidelity', ['exploratory', 'hardware_fidelity'] as const),
    material_library_fingerprint: requireString(value, 'material_library_fingerprint'),
    rig_definition_fingerprint: requireString(value, 'rig_definition_fingerprint'),
    biological_testing: false,
    notes: typeof value.notes === 'string' ? value.notes : '',
  };
}

function describeRejectedRequest(status: number, payload: unknown, label: string): string {
  if (!isRecord(payload)) return `${label} rejected the request (HTTP ${status}).`;
  const detail = payload.detail;
  if (typeof detail === 'string') return `${label} rejected the request (HTTP ${status}): ${detail}`;
  if (!isRecord(detail)) return `${label} rejected the request (HTTP ${status}).`;
  const code = typeof detail.code === 'string' ? detail.code : null;
  const reasons = Array.isArray(detail.reasons)
    ? detail.reasons.filter((entry): entry is string => typeof entry === 'string')
    : [];
  const readiness = isRecord(detail.readiness) ? detail.readiness : null;
  const missing = readiness && Array.isArray(readiness.missing_required_measurements)
    ? readiness.missing_required_measurements.filter((entry): entry is string => typeof entry === 'string')
    : [];
  const parts = [`${label} rejected the request (HTTP ${status})`];
  if (code) parts.push(`code: ${code}`);
  if (reasons.length) parts.push(`reasons: ${reasons.join(', ')}`);
  if (missing.length) parts.push(`missing measurements: ${missing.join(', ')}`);
  return `${parts.join('; ')}.`;
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    throw new Error(`API returned non-JSON content (HTTP ${response.status}).`);
  }
}

export async function fetchPreviewHealth(signal?: AbortSignal): Promise<PreviewApiHealth> {
  const response = await fetch(endpoint('/api/v1/health'), { signal });
  const payload = await readJson(response);
  if (!response.ok) throw new Error(`Preview API health check failed (HTTP ${response.status}).`);
  if (!isRecord(payload)) throw new Error('Preview API health response must be an object.');

  const status = requireString(payload, 'status');
  const scope = requireString(payload, 'scope');
  const solverExecution = requireBoolean(payload, 'solver_execution');
  const apiVersion = requireString(payload, 'api_version');

  if (status !== 'ok') throw new Error(`Preview API reported status ${status}.`);
  if (scope !== 'preview_geometry_only') throw new Error(`Unexpected Preview API scope: ${scope}.`);
  if (solverExecution !== false) throw new Error('Preview API boundary violation: solver execution must be disabled.');

  return { status: 'ok', apiVersion, scope: 'preview_geometry_only', solverExecution: false };
}

export async function fetchRigTemplate(signal?: AbortSignal): Promise<Record<string, unknown>> {
  const response = await fetch(endpoint('/api/v1/rig/template'), { signal });
  const payload = await readJson(response);
  if (!response.ok) throw new Error(`Rig template request failed (HTTP ${response.status}).`);
  if (!isRecord(payload)) throw new Error('Rig template response must be a JSON object.');
  return payload;
}

export async function fetchMaterialCatalog(signal?: AbortSignal): Promise<MaterialCatalog> {
  const response = await fetch(endpoint('/api/v1/materials'), { signal });
  const payload = await readJson(response);
  if (!response.ok) throw new Error(`Material catalog request failed (HTTP ${response.status}).`);
  return parseMaterialCatalog(payload);
}

export async function requestRigPreview(rigManifest: unknown, signal?: AbortSignal): Promise<PreviewApiResult> {
  const response = await fetch(endpoint('/api/v1/rig/preview'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(rigManifest),
    signal,
  });
  const payload = await readJson(response);
  if (!response.ok) throw new Error(describeRejectedRequest(response.status, payload, 'Preview API'));
  return parseApiResult(payload);
}

export async function fetchExperimentTemplate(rigManifest: unknown, signal?: AbortSignal): Promise<ExperimentConfig> {
  const response = await fetch(endpoint('/api/v1/experiment/template'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(rigManifest),
    signal,
  });
  const payload = await readJson(response);
  if (!response.ok) throw new Error(describeRejectedRequest(response.status, payload, 'Experiment API'));
  return parseExperimentConfig(payload);
}

export async function validateExperiment(experiment: ExperimentConfig, signal?: AbortSignal): Promise<ExperimentValidationResult> {
  const response = await fetch(endpoint('/api/v1/experiment/validate'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(experiment),
    signal,
  });
  const payload = await readJson(response);
  if (!response.ok) throw new Error(describeRejectedRequest(response.status, payload, 'Experiment API'));
  if (!isRecord(payload)) throw new Error('Experiment validation response must be an object.');
  if (payload.accepted !== true || payload.solver_execution !== false) {
    throw new Error('Experiment API boundary violation: validation must be accepted without solver execution.');
  }
  return {
    accepted: true,
    physics_state_hash: requireString(payload, 'physics_state_hash'),
    solver_execution: false,
    experiment: parseExperimentConfig(payload.experiment),
  };
}
