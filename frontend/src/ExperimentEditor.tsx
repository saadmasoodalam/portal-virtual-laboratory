import type { CoilDriveState, DriveMode, ExperimentConfig } from './api';

interface ExperimentEditorProps {
  experiment: ExperimentConfig;
  busy: boolean;
  physicsStateHash: string | null;
  onChange: (experiment: ExperimentConfig) => void;
  onValidate: () => void;
  onDownload: () => void;
  onBackToRig: () => void;
}

function canonicalModeChange(drive: CoilDriveState, mode: DriveMode): CoilDriveState {
  if (mode === 'off') {
    return { mode: 'off', current_a: 0, polarity: 1, frequency_hz: null, phase_rad: 0, omega_sign: 1 };
  }
  if (mode === 'dc') {
    return { ...drive, mode: 'dc', frequency_hz: null, phase_rad: 0, omega_sign: 1 };
  }
  return { ...drive, mode: 'harmonic' };
}

function updateDrive(experiment: ExperimentConfig, key: 'coil_a' | 'coil_b', drive: CoilDriveState): ExperimentConfig {
  return { ...experiment, [key]: drive };
}

interface CoilEditorProps {
  label: string;
  drive: CoilDriveState;
  onChange: (drive: CoilDriveState) => void;
}

function CoilEditor({ label, drive, onChange }: CoilEditorProps) {
  return (
    <section className="coil-drive-card">
      <div className="measurement-group-heading">
        <h3>{label}</h3>
        <span>{drive.mode}</span>
      </div>
      <div className="drive-grid">
        <label>
          <span>Drive mode</span>
          <select value={drive.mode} onChange={(event) => onChange(canonicalModeChange(drive, event.currentTarget.value as DriveMode))}>
            <option value="off">Off</option>
            <option value="dc">DC</option>
            <option value="harmonic">Harmonic</option>
          </select>
        </label>

        <label>
          <span>Current magnitude (A)</span>
          <input
            type="number"
            min="0"
            step="any"
            disabled={drive.mode === 'off'}
            value={drive.current_a}
            onChange={(event) => onChange({ ...drive, current_a: Number(event.currentTarget.value) })}
          />
        </label>

        <label>
          <span>Polarity</span>
          <select
            disabled={drive.mode === 'off'}
            value={drive.polarity}
            onChange={(event) => onChange({ ...drive, polarity: Number(event.currentTarget.value) as -1 | 1 })}
          >
            <option value={1}>+1</option>
            <option value={-1}>−1</option>
          </select>
        </label>

        <label>
          <span>Frequency (Hz)</span>
          <input
            type="number"
            min="0"
            step="any"
            disabled={drive.mode !== 'harmonic'}
            value={drive.frequency_hz ?? ''}
            placeholder="required for harmonic"
            onChange={(event) => onChange({ ...drive, frequency_hz: event.currentTarget.value === '' ? null : Number(event.currentTarget.value) })}
          />
        </label>

        <label>
          <span>Phase (rad)</span>
          <input
            type="number"
            step="any"
            disabled={drive.mode !== 'harmonic'}
            value={drive.phase_rad}
            onChange={(event) => onChange({ ...drive, phase_rad: Number(event.currentTarget.value) })}
          />
        </label>

        <label>
          <span>Signed-frequency convention</span>
          <select
            disabled={drive.mode !== 'harmonic'}
            value={drive.omega_sign}
            onChange={(event) => onChange({ ...drive, omega_sign: Number(event.currentTarget.value) as -1 | 1 })}
          >
            <option value={1}>+ω</option>
            <option value={-1}>−ω</option>
          </select>
        </label>
      </div>
      <p className="drive-note">
        {drive.mode === 'off' && 'OFF is stored as the canonical zero state.'}
        {drive.mode === 'dc' && 'DC polarity controls field/current reversal; frequency, phase and signed-frequency state are disabled.'}
        {drive.mode === 'harmonic' && 'For the present coaxial EM model, ±ω is a harmonic phase/frequency convention only. It is not interpreted as spacetime or portal rotation.'}
      </p>
    </section>
  );
}

export function ExperimentEditor({
  experiment,
  busy,
  physicsStateHash,
  onChange,
  onValidate,
  onDownload,
  onBackToRig,
}: ExperimentEditorProps) {
  return (
    <section className="experiment-editor">
      <div className="editor-toolbar">
        <div>
          <p className="eyebrow">PVL-2K experiment state</p>
          <h2>Electromagnetic Excitation Editor</h2>
          <p className="muted editor-intro">
            Declare Coil A and Coil B excitation independently. This screen validates experiment configuration only; it does not execute Gmsh, GetDP, or any solver job.
          </p>
        </div>
        <div className="editor-actions">
          <button type="button" className="secondary-button" onClick={onBackToRig}>Back to Rig</button>
          <button type="button" className="secondary-button" onClick={onDownload}>Download experiment JSON</button>
          <button type="button" className="primary-button" onClick={onValidate} disabled={busy}>{busy ? 'Validating…' : 'Validate experiment'}</button>
        </div>
      </div>

      <div className="experiment-meta-grid">
        <label><span>Experiment ID</span><input value={experiment.experiment_id} onChange={(event) => onChange({ ...experiment, experiment_id: event.currentTarget.value })} /></label>
        <label><span>Purpose</span><select value={experiment.purpose} onChange={(event) => onChange({ ...experiment, purpose: event.currentTarget.value as ExperimentConfig['purpose'] })}><option value="baseline">Baseline</option><option value="calibration">Calibration</option><option value="validation">Validation</option><option value="sweep">Sweep</option></select></label>
        <label><span>Duration (s)</span><input type="number" min="0" step="any" value={experiment.duration_s} onChange={(event) => onChange({ ...experiment, duration_s: Number(event.currentTarget.value) })} /></label>
        <label><span>Repetitions</span><input type="number" min="1" step="1" value={experiment.repetitions} onChange={(event) => onChange({ ...experiment, repetitions: Number(event.currentTarget.value) })} /></label>
        <label><span>Randomization seed</span><input type="number" min="0" step="1" value={experiment.randomization_seed} onChange={(event) => onChange({ ...experiment, randomization_seed: Number(event.currentTarget.value) })} /></label>
      </div>

      <div className="experiment-locks">
        <div><span>Sample medium</span><strong>{experiment.medium}</strong><small>Derived from the current Rig manifest.</small></div>
        <div><span>Copper boundary</span><strong>{experiment.copper_boundary_state}</strong><small>Derived from the current Rig manifest.</small></div>
        <div><span>Solver fidelity</span><strong>{experiment.solver_fidelity}</strong><small>Execution remains disabled in PVL-2K.</small></div>
        <div><span>Biological testing</span><strong>disabled</strong><small>Hard-coded false by the experiment model.</small></div>
      </div>

      <div className="coil-drive-grid">
        <CoilEditor label="Coil A" drive={experiment.coil_a} onChange={(drive) => onChange(updateDrive(experiment, 'coil_a', drive))} />
        <CoilEditor label="Coil B" drive={experiment.coil_b} onChange={(drive) => onChange(updateDrive(experiment, 'coil_b', drive))} />
      </div>

      <label className="experiment-notes"><span>Notes</span><textarea value={experiment.notes} onChange={(event) => onChange({ ...experiment, notes: event.currentTarget.value })} /></label>

      {physicsStateHash && (
        <div className="validation-success">
          Experiment model accepted without solver execution. Physics-state hash: <code>{physicsStateHash}</code>
        </div>
      )}
    </section>
  );
}
