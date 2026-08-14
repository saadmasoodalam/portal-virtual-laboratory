import { useMemo } from 'react';

import type { MaterialCatalog } from './api';
import { RigConfigurationEditor } from './RigConfigurationEditor';
import {
  listMeasurements,
  measurementLabel,
  summarizeMeasurements,
  topLevelGroup,
  updateMeasurement,
  type MeasurementEntry,
  type MeasurementStatus,
} from './rigManifest';

interface RigManifestEditorProps {
  manifest: Record<string, unknown>;
  sourceName: string;
  busy: boolean;
  materialCatalog: MaterialCatalog;
  onChange: (manifest: Record<string, unknown>) => void;
  onPreview: () => void;
  onDownload: () => void;
  onReset: () => void;
}

const statusOptions: readonly { value: MeasurementStatus; label: string }[] = [
  { value: 'unknown', label: 'Unknown' },
  { value: 'illustrative', label: 'Illustrative' },
  { value: 'measured', label: 'Measured' },
  { value: 'supplier', label: 'Supplier' },
];

function groupTitle(group: string): string {
  return group.replaceAll('_', ' ');
}

function unitLabel(entry: MeasurementEntry): string {
  return entry.valueKey === 'value' ? 'count' : 'm';
}

export function RigManifestEditor({
  manifest,
  sourceName,
  busy,
  materialCatalog,
  onChange,
  onPreview,
  onDownload,
  onReset,
}: RigManifestEditorProps) {
  const entries = useMemo(() => listMeasurements(manifest), [manifest]);
  const summary = useMemo(() => summarizeMeasurements(manifest), [manifest]);
  const groups = useMemo(() => {
    const result = new Map<string, MeasurementEntry[]>();
    entries.forEach((entry) => {
      const group = topLevelGroup(entry);
      const bucket = result.get(group) ?? [];
      bucket.push(entry);
      result.set(group, bucket);
    });
    return [...result.entries()];
  }, [entries]);

  function setMeasurement(entry: MeasurementEntry, patch: Parameters<typeof updateMeasurement>[2]) {
    onChange(updateMeasurement(manifest, entry, patch));
  }

  return (
    <section className="manifest-editor">
      <div className="editor-toolbar">
        <div>
          <p className="eyebrow">PVL-2J controlled input</p>
          <h2>Rig Manifest Editor</h2>
          <p className="muted editor-intro">
            Enter only known dimensions, record provenance, and select controlled materials and boundary states from the versioned backend catalog.
          </p>
        </div>
        <div className="editor-actions">
          <button type="button" className="secondary-button" onClick={onReset} disabled={busy}>Reset template</button>
          <button type="button" className="secondary-button" onClick={onDownload} disabled={busy}>Download JSON</button>
          <button type="button" className="primary-button" onClick={onPreview} disabled={busy || summary.missingRequired > 0}>
            {busy ? 'Validating…' : 'Validate & preview'}
          </button>
        </div>
      </div>

      <div className="editor-status-grid">
        <div><span>Source</span><strong>{sourceName}</strong></div>
        <div><span>Measurements</span><strong>{summary.total}</strong></div>
        <div><span>Missing required</span><strong>{summary.missingRequired}</strong></div>
        <div><span>Illustrative</span><strong>{summary.illustrative}</strong></div>
        <div><span>Measured / supplier</span><strong>{summary.hardwareFidelity}</strong></div>
      </div>

      <RigConfigurationEditor manifest={manifest} catalog={materialCatalog} onChange={onChange} />

      {summary.missingRequired > 0 && (
        <div className="editor-notice">
          Preview remains disabled until every solver-required measurement has a value and a non-unknown provenance status. This is a completeness gate only; measured/supplier provenance is required later for hardware fidelity.
        </div>
      )}

      <div className="measurement-groups">
        {groups.map(([group, measurements]) => (
          <section className="measurement-group" key={group}>
            <div className="measurement-group-heading">
              <h3>{groupTitle(group)}</h3>
              <span>{measurements.length} fields</span>
            </div>
            <div className="measurement-table">
              {measurements.map((entry) => (
                <div className="measurement-row" key={entry.displayPath}>
                  <div className="measurement-name">
                    <strong>{measurementLabel(entry)}</strong>
                    <small className="mono">{entry.displayPath}</small>
                  </div>
                  <label>
                    <span>Provenance</span>
                    <select
                      value={entry.status}
                      onChange={(event) => setMeasurement(entry, { status: event.currentTarget.value as MeasurementStatus })}
                    >
                      {statusOptions.map((option) => (
                        <option key={option.value} value={option.value}>{option.label}</option>
                      ))}
                    </select>
                  </label>
                  <label>
                    <span>Value ({unitLabel(entry)})</span>
                    <input
                      type="number"
                      step={entry.valueKey === 'value' ? 1 : 'any'}
                      value={entry.value ?? ''}
                      disabled={entry.status === 'unknown'}
                      onChange={(event) => {
                        const raw = event.currentTarget.value;
                        setMeasurement(entry, { value: raw === '' ? null : Number(raw) });
                      }}
                    />
                  </label>
                  <label className="source-note-field">
                    <span>Source note</span>
                    <input
                      type="text"
                      value={entry.sourceNote}
                      placeholder={entry.status === 'measured' ? 'e.g. caliper measurement, 2026-08-14' : entry.status === 'supplier' ? 'e.g. datasheet/model reference' : 'optional note'}
                      onChange={(event) => setMeasurement(entry, { sourceNote: event.currentTarget.value })}
                    />
                  </label>
                  <span className={`measurement-status status-${entry.status}`}>
                    {entry.requiredForSolver ? 'required' : 'optional'}
                  </span>
                </div>
              ))}
            </div>
          </section>
        ))}
      </div>
    </section>
  );
}
