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

const configuredBase = (import.meta.env.VITE_PVL_API_BASE_URL ?? '').trim();
const apiBase = configuredBase.endsWith('/') ? configuredBase.slice(0, -1) : configuredBase;

function isDcPlanResult(value: unknown): value is DcPlanResult {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
  const record = value as Record<string, unknown>;
  return typeof record.plan_hash === 'string'
    && typeof record.current_a === 'number'
    && typeof record.run_count === 'number'
    && typeof record.repetitions === 'number'
    && typeof record.randomization_seed === 'number'
    && record.solver_execution === false
    && Array.isArray(record.runs);
}

export async function planDcExperiment(experiment: ExperimentConfig, currentA: number): Promise<DcPlanResult> {
  const response = await fetch(`${apiBase}/api/v1/experiment/plan/dc`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ experiment, current_a: currentA }),
  });
  const payload: unknown = await response.json();
  if (!response.ok) throw new Error(`DC planner rejected the request (HTTP ${response.status}).`);
  if (!isDcPlanResult(payload)) throw new Error('DC planner returned an invalid response.');
  return payload;
}
