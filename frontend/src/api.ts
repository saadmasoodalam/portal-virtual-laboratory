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
    throw new Error(`Preview API response field ${key} must be a non-empty string.`);
  }
  return value;
}

function requireBoolean(record: Record<string, unknown>, key: string): boolean {
  const value = record[key];
  if (typeof value !== 'boolean') {
    throw new Error(`Preview API response field ${key} must be boolean.`);
  }
  return value;
}

function requireStringArray(record: Record<string, unknown>, key: string): string[] {
  const value = record[key];
  if (!Array.isArray(value) || value.some((entry) => typeof entry !== 'string')) {
    throw new Error(`Preview API response field ${key} must be a string array.`);
  }
  return [...value];
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

function describeRejectedRequest(status: number, payload: unknown): string {
  if (!isRecord(payload) || !isRecord(payload.detail)) {
    return `Preview API rejected the Rig manifest (HTTP ${status}).`;
  }

  const detail = payload.detail;
  const reasons = Array.isArray(detail.reasons)
    ? detail.reasons.filter((entry): entry is string => typeof entry === 'string')
    : [];
  const readiness = isRecord(detail.readiness) ? detail.readiness : null;
  const missing = readiness && Array.isArray(readiness.missing_required_measurements)
    ? readiness.missing_required_measurements.filter((entry): entry is string => typeof entry === 'string')
    : [];

  const parts = [`Preview API rejected the Rig manifest (HTTP ${status})`];
  if (reasons.length) parts.push(`reasons: ${reasons.join(', ')}`);
  if (missing.length) parts.push(`missing measurements: ${missing.join(', ')}`);
  return `${parts.join('; ')}.`;
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    throw new Error(`Preview API returned non-JSON content (HTTP ${response.status}).`);
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

export async function requestRigPreview(rigManifest: unknown, signal?: AbortSignal): Promise<PreviewApiResult> {
  const response = await fetch(endpoint('/api/v1/rig/preview'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(rigManifest),
    signal,
  });
  const payload = await readJson(response);
  if (!response.ok) throw new Error(describeRejectedRequest(response.status, payload));
  return parseApiResult(payload);
}
