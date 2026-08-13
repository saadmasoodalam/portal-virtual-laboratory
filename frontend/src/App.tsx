import { useMemo, useState } from 'react';

import { fetchRigTemplate, requestRigPreview } from './api';
import { parsePreviewScene } from './parsePreviewScene';
import { RigManifestEditor } from './RigManifestEditor';
import { PreviewRigCanvas } from './scene/PreviewRigCanvas';
import type { PreviewScene } from './types';

function meters(value: number): string {
  if (Math.abs(value) >= 1) return `${value.toFixed(3)} m`;
  return `${(value * 1000).toFixed(1)} mm`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isPreviewDocument(value: unknown): boolean {
  return isRecord(value) && value.fidelity === 'illustrative_geometry';
}

export default function App() {
  const [scene, setScene] = useState<PreviewScene | null>(null);
  const [manifest, setManifest] = useState<Record<string, unknown> | null>(null);
  const [manifestSourceName, setManifestSourceName] = useState('canonical API template');
  const [view, setView] = useState<'editor' | 'preview'>('preview');
  const [hidden, setHidden] = useState<Set<string>>(() => new Set());
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [source, setSource] = useState<'api' | 'local' | null>(null);
  const [busy, setBusy] = useState(false);

  const selectedItem = useMemo(
    () => scene?.items.find((item) => item.component_id === selected) ?? null,
    [scene, selected],
  );

  async function startNewManifest() {
    setBusy(true);
    setError(null);
    try {
      const template = await fetchRigTemplate();
      setManifest(template);
      setManifestSourceName('canonical API template');
      setView('editor');
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to load the Rig template.');
    } finally {
      setBusy(false);
    }
  }

  async function loadFile(file: File) {
    setError(null);
    try {
      const document = JSON.parse(await file.text()) as unknown;
      if (isPreviewDocument(document)) {
        setScene(parsePreviewScene(document));
        setSource('local');
        setFileName(file.name);
        setManifest(null);
        setView('preview');
      } else {
        if (!isRecord(document)) throw new Error('Rig manifest must be a JSON object.');
        setManifest(document);
        setManifestSourceName(file.name);
        setScene(null);
        setSource(null);
        setFileName(file.name);
        setView('editor');
      }
      setHidden(new Set());
      setSelected(null);
    } catch (caught) {
      setScene(null);
      setManifest(null);
      setSource(null);
      setFileName(null);
      setSelected(null);
      setError(caught instanceof Error ? caught.message : 'Unable to load Rig or preview JSON.');
    }
  }

  async function previewManifest() {
    if (!manifest) return;
    setBusy(true);
    setError(null);
    try {
      const result = await requestRigPreview(manifest);
      setScene(result.scene);
      setSource('api');
      setFileName(manifestSourceName);
      setHidden(new Set());
      setSelected(null);
      setView('preview');
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to validate the Rig manifest.');
    } finally {
      setBusy(false);
    }
  }

  function downloadManifest() {
    if (!manifest) return;
    const blob = new Blob([`${JSON.stringify(manifest, null, 2)}\n`], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'pvl-rig-v1-manifest.json';
    anchor.click();
    URL.revokeObjectURL(url);
  }

  function toggleComponent(componentId: string) {
    setHidden((current) => {
      const next = new Set(current);
      if (next.has(componentId)) next.delete(componentId);
      else next.add(componentId);
      return next;
    });
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Portal Virtual Laboratory</p>
          <h1>Rig Geometry Laboratory</h1>
        </div>
        <div className="topbar-actions">
          {manifest && view === 'preview' && (
            <button type="button" className="secondary-button" onClick={() => setView('editor')}>Edit Rig</button>
          )}
          <button type="button" className="secondary-button" onClick={() => void startNewManifest()} disabled={busy}>
            New Rig manifest
          </button>
          <label className="load-button">
            Load Rig / preview JSON
            <input
              type="file"
              accept="application/json,.json"
              onChange={(event) => {
                const file = event.currentTarget.files?.[0];
                if (file) void loadFile(file);
                event.currentTarget.value = '';
              }}
            />
          </label>
        </div>
      </header>

      <div className="boundary-banner">
        <strong>PVL-2I boundary:</strong> dimensions and provenance can now be edited, but no solver can be started from this interface. <code>illustrative</code> values are preview-only; hardware-fidelity readiness requires <code>measured</code> or <code>supplier</code> provenance. Existing preview JSON remains a local diagnostic path only.
      </div>

      {error && <div className="error-panel">{error}</div>}

      {view === 'editor' && manifest ? (
        <RigManifestEditor
          manifest={manifest}
          sourceName={manifestSourceName}
          busy={busy}
          onChange={setManifest}
          onPreview={() => void previewManifest()}
          onDownload={downloadManifest}
          onReset={() => void startNewManifest()}
        />
      ) : !scene ? (
        <section className="empty-state">
          <div>
            <p className="eyebrow">PVL-2I</p>
            <h2>Create a controlled Rig manifest or load an existing file.</h2>
            <p>Use the canonical template to enter dimensions with explicit provenance, then validate the manifest through the FastAPI preview boundary. Solver execution remains disabled.</p>
            <button type="button" className="primary-button empty-action" onClick={() => void startNewManifest()} disabled={busy}>
              {busy ? 'Loading…' : 'Create Rig manifest'}
            </button>
          </div>
        </section>
      ) : (
        <section className="workspace">
          <aside className="sidebar component-panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Scene</p>
                <h2>{scene.rig_id}</h2>
              </div>
              <span className="status-chip">Illustrative</span>
            </div>
            <dl className="scene-meta">
              <div><dt>File</dt><dd>{fileName}</dd></div>
              <div><dt>Source</dt><dd>{source === 'api' ? 'Validated preview API' : 'Local diagnostic file'}</dd></div>
              <div><dt>Fingerprint</dt><dd className="mono">{scene.geometry_fingerprint.slice(0, 12)}…</dd></div>
              <div><dt>Components</dt><dd>{scene.items.length}</dd></div>
            </dl>
            <h3>Components</h3>
            <div className="component-list">
              {scene.items.map((item) => (
                <button
                  type="button"
                  key={item.component_id}
                  className={`component-row ${selected === item.component_id ? 'selected' : ''}`}
                  onClick={() => setSelected(item.component_id)}
                >
                  <input
                    type="checkbox"
                    checked={!hidden.has(item.component_id)}
                    aria-label={`Show ${item.component_id}`}
                    onClick={(event) => event.stopPropagation()}
                    onChange={() => toggleComponent(item.component_id)}
                  />
                  <span>
                    <strong>{item.component_id}</strong>
                    <small>{item.primitive}</small>
                  </span>
                </button>
              ))}
            </div>
          </aside>

          <div className="viewer-panel">
            <PreviewRigCanvas scene={scene} hidden={hidden} selected={selected} onSelect={setSelected} />
            <div className="viewer-hint">Orbit: drag · Pan: right-drag · Zoom: wheel · Z axis is up</div>
          </div>

          <aside className="sidebar inspector-panel">
            <p className="eyebrow">Inspector</p>
            {!selectedItem ? (
              <p className="muted">Select a component in the scene or component list.</p>
            ) : (
              <>
                <h2>{selectedItem.component_id}</h2>
                <dl className="scene-meta inspector-data">
                  <div><dt>Primitive</dt><dd>{selectedItem.primitive}</dd></div>
                  <div><dt>Material</dt><dd>{selectedItem.material_id ?? 'none'}</dd></div>
                  <div><dt>Center X</dt><dd>{meters(selectedItem.center_m[0])}</dd></div>
                  <div><dt>Center Y</dt><dd>{meters(selectedItem.center_m[1])}</dd></div>
                  <div><dt>Center Z</dt><dd>{meters(selectedItem.center_m[2])}</dd></div>
                </dl>
                <h3>Parameters</h3>
                <dl className="scene-meta inspector-data">
                  {Object.entries(selectedItem.parameters_m).map(([key, value]) => (
                    <div key={key}><dt>{key}</dt><dd>{meters(value)}</dd></div>
                  ))}
                  {Object.entries(selectedItem.integer_parameters).map(([key, value]) => (
                    <div key={key}><dt>{key}</dt><dd>{value}</dd></div>
                  ))}
                </dl>
              </>
            )}
          </aside>
        </section>
      )}
    </main>
  );
}
