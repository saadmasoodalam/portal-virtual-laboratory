import { useEffect, useState } from 'react';

import type { ExperimentConfig } from './api';
import {
  persistDcExperimentPackage,
  planDcExperiment,
  type DcPlanResult,
  type ExperimentPackageResult,
} from './dcPlanApi';

interface DcPlanEditorProps {
  experiment: ExperimentConfig;
}

function signedCurrent(mode: string, current: number, polarity: number): string {
  if (mode === 'off') return 'OFF';
  return `${polarity * current >= 0 ? '+' : ''}${(polarity * current).toFixed(3)} A`;
}

export function DcPlanEditor({ experiment }: DcPlanEditorProps) {
  const [currentA, setCurrentA] = useState(1.0);
  const [busy, setBusy] = useState(false);
  const [plan, setPlan] = useState<DcPlanResult | null>(null);
  const [packageResult, setPackageResult] = useState<ExperimentPackageResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setPlan(null);
    setPackageResult(null);
    setError(null);
  }, [experiment]);

  async function buildPlan() {
    setBusy(true);
    setPlan(null);
    setPackageResult(null);
    setError(null);
    try {
      const result = await planDcExperiment(experiment, currentA);
      setPlan(result);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to create DC plan.');
    } finally {
      setBusy(false);
    }
  }

  async function persistPackage() {
    if (!plan) return;
    setBusy(true);
    setPackageResult(null);
    setError(null);
    try {
      const result = await persistDcExperimentPackage(experiment, currentA);
      if (result.plan_hash !== plan.plan_hash) {
        throw new Error('Persistence boundary rejected: returned package does not match the displayed plan hash.');
      }
      setPackageResult(result);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to persist scientific package.');
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
          <p className="eyebrow">PVL-2M package persistence</p>
          <h2>Rig v1 DC Run-Matrix Planner</h2>
          <p className="muted editor-intro">
            Generate the controlled DC matrix, then persist it as an integrity-checksummed scientific package. Persistence creates planned run manifests and empty raw-data directories only; it does not execute FEM.
          </p>
        </div>
        <button type="button" className="secondary-button" disabled={!plan} onClick={downloadPlan}>Download plan JSON</button>
      </div>

      <div className="dc-plan-controls">
        <label>
          <span>DC current magnitude (A)</span>
          <input
            type="number"
            min="0.000001"
            step="any"
            value={currentA}
            onChange={(event) => {
              setCurrentA(Number(event.currentTarget.value));
              setPlan(null);
              setPackageResult(null);
            }}
          />
        </label>
        <div><span>Repetitions</span><strong>{experiment.repetitions}</strong><small>From experiment configuration.</small></div>
        <div><span>Randomization seed</span><strong>{experiment.randomization_seed}</strong><small>Same seed produces the same active-state order.</small></div>
        <button type="button" className="primary-button" disabled={busy || currentA <= 0} onClick={() => void buildPlan()}>{busy && !plan ? 'Planning…' : 'Plan DC matrix'}</button>
      </div>

      <div className="editor-notice">
        Every repetition begins with OFF/OFF, followed by a seeded shuffle of eight active states. Opposed DC states use coil polarity; signed frequency remains +1 for DC. Package persistence never creates solver outputs.
      </div>

      {error && <div className="error-panel">{error}</div>}

      {plan && (
        <>
          <div className="plan-summary-grid">
            <div><span>Runs</span><strong>{plan.run_count}</strong></div>
            <div><span>Current</span><strong>{plan.current_a} A</strong></div>
            <div><span>Seed</span><strong>{plan.randomization_seed}</strong></div>
            <div><span>Plan hash</span><strong className="mono">{plan.plan_hash.slice(0, 16)}…</strong></div>
            <div><span>Solver execution</span><strong>disabled</strong></div>
          </div>

          <div className="package-persistence-panel">
            <div>
              <span>Scientific package</span>
              <strong>{packageResult ? packageResult.package_id : 'Not persisted'}</strong>
              <small>Writes experiment.json, run_matrix.json, package_manifest.json, checksums.json, planned run manifests, and empty raw/ directories.</small>
            </div>
            <button
              type="button"
              className="primary-button"
              disabled={busy || packageResult !== null}
              onClick={() => void persistPackage()}
            >
              {busy ? 'Persisting…' : packageResult ? 'Package persisted' : 'Persist scientific package'}
            </button>
          </div>

          {packageResult && (
            <div className="package-success">
              <div><span>Package fingerprint</span><code>{packageResult.package_fingerprint}</code></div>
              <div><span>Stored under</span><code>{packageResult.relative_path}</code></div>
              <div><span>Integrity files</span><strong>{packageResult.checksummed_files} files checksummed</strong></div>
              <div><span>Execution state</span><strong>planned only — solver disabled</strong></div>
            </div>
          )}

          <div className="plan-table-wrap">
            <table className="plan-table">
              <thead><tr><th>#</th><th>Rep</th><th>State</th><th>Coil A</th><th>Coil B</th><th>Physics hash</th></tr></thead>
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
