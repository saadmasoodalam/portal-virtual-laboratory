import { useState } from 'react';

import type { ExperimentConfig } from './api';
import { planDcExperiment, type DcPlanResult } from './dcPlanApi';

interface DcPlanEditorProps {
  experiment: ExperimentConfig;
  onBack: () => void;
  onError: (message: string | null) => void;
}

function signedCurrent(mode: string, current: number, polarity: number): string {
  if (mode === 'off') return 'OFF';
  return `${polarity * current >= 0 ? '+' : ''}${(polarity * current).toFixed(3)} A`;
}

export function DcPlanEditor({ experiment, onBack, onError }: DcPlanEditorProps) {
  const [currentA, setCurrentA] = useState(1.0);
  const [busy, setBusy] = useState(false);
  const [plan, setPlan] = useState<DcPlanResult | null>(null);

  async function buildPlan() {
    setBusy(true);
    setPlan(null);
    onError(null);
    try {
      const result = await planDcExperiment(experiment, currentA);
      setPlan(result);
    } catch (caught) {
      onError(caught instanceof Error ? caught.message : 'Unable to create DC plan.');
    } finally {
      setBusy(false);
    }
  }

  function downloadPlan() {
    if (!plan) return;
    const blob = new Blob([`${JSON.stringify(plan, null, 2)}\n`], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'pvl-rig-v1-dc-run-matrix.json';
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="dc-plan-editor">
      <div className="editor-toolbar">
        <div>
          <p className="eyebrow">PVL-2L planning only</p>
          <h2>Rig v1 DC Run-Matrix Planner</h2>
          <p className="muted editor-intro">
            Generate the documented OFF/A/B/same/opposed DC control matrix with a reproducible seeded run order. Planning creates no solver job and executes no FEM calculation.
          </p>
        </div>
        <div className="editor-actions">
          <button type="button" className="secondary-button" onClick={onBack}>Back to excitation</button>
          <button type="button" className="secondary-button" disabled={!plan} onClick={downloadPlan}>Download plan JSON</button>
        </div>
      </div>

      <div className="dc-plan-controls">
        <label>
          <span>DC current magnitude (A)</span>
          <input type="number" min="0.000001" step="any" value={currentA} onChange={(event) => { setCurrentA(Number(event.currentTarget.value)); setPlan(null); }} />
        </label>
        <div><span>Repetitions</span><strong>{experiment.repetitions}</strong><small>From experiment configuration.</small></div>
        <div><span>Randomization seed</span><strong>{experiment.randomization_seed}</strong><small>Same seed produces the same active-state order.</small></div>
        <button type="button" className="primary-button" disabled={busy || currentA <= 0} onClick={() => void buildPlan()}>{busy ? 'Planning…' : 'Plan DC matrix'}</button>
      </div>

      <div className="editor-notice">
        Every repetition begins with OFF/OFF, followed by a seeded shuffle of eight active states. Opposed DC states use coil polarity; signed frequency remains +1 for DC. This page cannot run the solver.
      </div>

      {plan && (
        <>
          <div className="plan-summary-grid">
            <div><span>Runs</span><strong>{plan.run_count}</strong></div>
            <div><span>Current</span><strong>{plan.current_a} A</strong></div>
            <div><span>Seed</span><strong>{plan.randomization_seed}</strong></div>
            <div><span>Plan hash</span><strong className="mono">{plan.plan_hash.slice(0, 16)}…</strong></div>
            <div><span>Solver execution</span><strong>disabled</strong></div>
          </div>

          <div className="plan-table-wrap">
            <table className="plan-table">
              <thead>
                <tr><th>#</th><th>Rep</th><th>State</th><th>Coil A</th><th>Coil B</th><th>Physics hash</th></tr>
              </thead>
              <tbody>
                {plan.runs.map((run) => (
                  <tr key={run.run_id}>
                    <td>{run.sequence_index}</td>
                    <td>{run.repetition_index}</td>
                    <td><strong>{run.state_id}</strong><small>{run.run_id}</small></td>
                    <td>{signedCurrent(run.coil_a.mode, run.coil_a.current_a, run.coil_a.polarity)}</td>
                    <td>{signedCurrent(run.coil_b.mode, run.coil_b.current_a, run.coil_b.polarity)}</td>
                    <td className="mono">{run.physics_state_hash.slice(0, 12)}…</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
