import type { CoilDriveState, ExperimentConfig } from './api';

export interface DcPlannedRun {
  run_id: string;
  sequence_index: number;
  repetition_index: number;
  state_id: string;
  configuration_hash: string;
  physics_state_hash: string;
  coil_a: CoilDriveState;
  coil_b: CoilDriveState;
}

export interface DcPlanResult {
  plan_hash: string;
  current_a: number;
  run_count: number;
  repetitions: number;
  randomization_seed: number;
  solver_execution: false;
  runs: DcPlannedRun[];
}

export interface ExperimentPackageResult {
  package_id: string;
  plan_hash: string;
  package_fingerprint: string;
  configuration_hash: string;
  physics_state_hash: string;
  run_count: number;
  relative_path: string;
  checksummed_files: number;
  solver_execution: false;
}

const configuredBase = (import.meta.env.VITE_PVL_API_BASE_URL ?? '').trim();
const apiBase = configuredBase.endsWith('/') ? configuredBase.slice(0, -1) : configuredBase;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isDcPlanResult(value: unknown): value is DcPlanResult {
  if (!isRecord(value)) return false;
  return typeof value.plan_hash === 'string'
    && typeof value.current_a === 'number'
    && typeof value.run_count === 'number'
    && typeof value.repetitions === 'number'
    && typeof value.randomization_seed === 'number'
    && value.solver_execution === false
    && Array.isArray(value.runs);
}

function isExperimentPackageResult(value: unknown): value is ExperimentPackageResult {
  if (!isRecord(value)) return false;
  return typeof value.package_id === 'string'
    && typeof value.plan_hash === 'string'
    && typeof value.package_fingerprint === 'string'
    && typeof value.configuration_hash === 'string'
    && typeof value.physics_state_hash === 'string'
    && typeof value.run_count === 'number'
    && typeof value.relative_path === 'string'
    && typeof value.checksummed_files === 'number'
    && value.solver_execution === false;
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    throw new Error(`PVL API returned non-JSON content (HTTP ${response.status}).`);
  }
}

export async function planDcExperiment(experiment: ExperimentConfig, currentA: number): Promise<DcPlanResult> {
  const response = await fetch(`${apiBase}/api/v1/experiment/plan/dc`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ experiment, current_a: currentA }),
  });
  const payload = await readJson(response);
  if (!response.ok) throw new Error(`DC planner rejected the request (HTTP ${response.status}).`);
  if (!isDcPlanResult(payload)) throw new Error('DC planner returned an invalid response.');
  return payload;
}

export async function persistDcExperimentPackage(
  experiment: ExperimentConfig,
  currentA: number,
): Promise<ExperimentPackageResult> {
  const response = await fetch(`${apiBase}/api/v1/experiment/plan/dc/persist`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ experiment, current_a: currentA }),
  });
  const payload = await readJson(response);
  if (!response.ok) {
    if (response.status === 409) throw new Error('This exact scientific package already exists and was not overwritten.');
    throw new Error(`Package persistence rejected the request (HTTP ${response.status}).`);
  }
  if (!isExperimentPackageResult(payload)) throw new Error('Package persistence returned an invalid response.');
  return payload;
}
