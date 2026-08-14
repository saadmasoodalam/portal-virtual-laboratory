import { useEffect, useState } from 'react';

import {
  fetchScientificRunCatalog,
  fetchScientificRunDetail,
  type ScientificRunDetail,
  type ScientificRunSummary,
} from './resultsApi';

function formatMetric(value: number): string {
  const magnitude = Math.abs(value);
  if ((magnitude !== 0 && magnitude < 1e-3) || magnitude >= 1e4) return value.toExponential(6);
  return value.toFixed(6).replace(/0+$/, '').replace(/\.$/, '');
}

function shortHash(value: string): string {
  return value.length > 16 ? `${value.slice(0, 16)}…` : value;
}

export interface ResultsDashboardProps {
  initialExperimentId?: string;
  onBack: () => void;
}

export function ResultsDashboard({ initialExperimentId = '', onBack }: ResultsDashboardProps) {
  const [experimentId, setExperimentId] = useState(initialExperimentId);
  const [runs, setRuns] = useState<ScientificRunSummary[]>([]);
  const [selected, setSelected] = useState<ScientificRunSummary | null>(null);
  const [detail, setDetail] = useState<ScientificRunDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setDetail(null);
  }, [selected]);

  async function loadCatalog() {
    setBusy(true);
    setError(null);
    setSelected(null);
    setDetail(null);
    try {
      const catalog = await fetchScientificRunCatalog(experimentId);
      setRuns(catalog.runs);
      if (catalog.runs.length) setSelected(catalog.runs[0]);
    } catch (caught) {
      setRuns([]);
      setError(caught instanceof Error ? caught.message : 'Unable to load scientific results.');
    } finally {
      setBusy(false);
    }
  }

  async function loadDetail(run: ScientificRunSummary) {
    setSelected(run);
    setBusy(true);
    setError(null);
    try {
      setDetail(await fetchScientificRunDetail(run));
    } catch (caught) {
      setDetail(null);
      setError(caught instanceof Error ? caught.message : 'Unable to load scientific result detail.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="editor-shell">
      <div className="editor-header">
        <div>
          <p className="eyebrow">Established-physics evidence</p>
          <h2>Scientific Results</h2>
          <p className="muted">Only checksum-verified persisted runs are listed. Portal-hypothesis interpretation is not performed here.</p>
        </div>
        <button type="button" className="secondary-button" onClick={onBack}>Back to laboratory</button>
      </div>

      <div className="boundary-banner">
        <strong>Evidence boundary:</strong> solver execution and numerical metrics are displayed separately from physical validation and hypothesis analysis.
      </div>

      {error && <div className="error-panel">{error}</div>}

      <div className="editor-grid">
        <section className="editor-card">
          <p className="eyebrow">Catalog</p>
          <h3>Experiment runs</h3>
          <label className="field-row">
            <span>Experiment ID</span>
            <input value={experimentId} onChange={(event) => setExperimentId(event.target.value)} placeholder="experiment-001" />
          </label>
          <button type="button" className="primary-button" disabled={busy || !experimentId.trim()} onClick={() => void loadCatalog()}>
            {busy ? 'Loading…' : 'Load verified runs'}
          </button>
          <div className="component-list">
            {runs.map((run) => (
              <button
                type="button"
                key={`${run.package_id}:${run.run_id}:${run.job_id}`}
                className={`component-row ${selected?.job_id === run.job_id ? 'selected' : ''}`}
                onClick={() => void loadDetail(run)}
              >
                <span>
                  <strong>{run.run_id}</strong>
                  <small>{run.solver_route} · {new Date(run.created_utc).toLocaleString()}</small>
                </span>
              </button>
            ))}
            {!busy && runs.length === 0 && <p className="muted">No verified runs loaded.</p>}
          </div>
        </section>

        <section className="editor-card">
          <p className="eyebrow">Run identity</p>
          {!selected ? (
            <p className="muted">Select a verified scientific run.</p>
          ) : (
            <dl className="scene-meta inspector-data">
              <div><dt>Run</dt><dd>{selected.run_id}</dd></div>
              <div><dt>Job</dt><dd className="mono">{selected.job_id}</dd></div>
              <div><dt>Solver route</dt><dd>{selected.solver_route}</dd></div>
              <div><dt>Solver executed</dt><dd>{selected.solver_execution ? 'yes' : 'no'}</dd></div>
              <div><dt>Checksum</dt><dd>verified</dd></div>
              <div><dt>Geometry</dt><dd>{selected.geometry_fidelity}</dd></div>
              <div><dt>Mesh hash</dt><dd className="mono">{shortHash(selected.mesh_configuration_hash)}</dd></div>
              <div><dt>Physical validation</dt><dd>{selected.physical_validation ? 'yes' : 'no'}</dd></div>
              <div><dt>Hypothesis analysis</dt><dd>{selected.hypothesis_analysis ? 'yes' : 'no'}</dd></div>
            </dl>
          )}
        </section>

        <section className="editor-card">
          <p className="eyebrow">Derived metrics</p>
          <h3>Numerical result</h3>
          {!detail ? (
            <p className="muted">Open a run to inspect normalized scientific metrics.</p>
          ) : Object.keys(detail.metrics).length === 0 ? (
            <p className="muted">This control run has no solver-derived scalar metrics.</p>
          ) : (
            <dl className="scene-meta inspector-data">
              {Object.entries(detail.metrics).sort(([a], [b]) => a.localeCompare(b)).map(([name, value]) => (
                <div key={name}><dt>{name}</dt><dd className="mono">{formatMetric(value)}</dd></div>
              ))}
            </dl>
          )}
        </section>
      </div>
    </section>
  );
}
