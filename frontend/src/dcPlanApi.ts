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

export async function planDcExperiment(_experiment: ExperimentConfig, _currentA: number): Promise<DcPlanResult> {
  throw new Error('DC planning client not yet connected.');
}
