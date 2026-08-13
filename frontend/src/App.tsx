import { useMemo, useState } from 'react';

import { requestRigPreview } from './api';
import { parsePreviewScene } from './parsePreviewScene';
import { PreviewRigCanvas } from './scene/PreviewRigCanvas';
import type { PreviewScene } from './types';

function meters(value: number): string {
  if (Math.abs(value) >= 1) return `${value.toFixed(3)} m`;
  return `${(value * 1000).toFixed(1)} mm`;
}

function isPreviewDocument(value: unknown): boolean {
  return typeof value === 'object'
    && value !== null
    && !Array.isArray(value)
    && (value as Record<string, unknown>).fidelity === 'illustrative_geometry';
}

export default function App() {
  const [scene, setScene] = useState<PreviewScene | null>(null);
  const [hidden, setHidden] = useState<Set<string>>(() => new Set());
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [source, setSource] = useState<'api' | 'local' | null>(null);

  const selectedItem = useMemo(
    () => scene?.items.find((item) => item.component_id === selected) ?? null,
    [scene, selected],
  );

  async function loadFile(file: File) {
    setError(null);
    try {
      const document = JSON.parse(await file.text()) as unknown;
      const loaded = isPreviewDocument(document)
        ? { scene: parsePreviewScene(document), source: 'local' as const }
        : { scene: (await requestRigPreview(document)).scene, source: 'api' as const };
      setScene(loaded.scene);
      setSource(loaded.source);
      setFileName(file.name);
      setHidden(new Set());
      setSelected(null);
    } catch (caught) {
      setScene(null);
      setSource(null);
      setFileName(null);
      setSelected(null);
      setError(caught instanceof Error ? caught.message : 'Unable to load Rig or preview JSON.');
    }
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
          <h1>Rig Geometry Preview</h1>
        </div>
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
      </header>

      <div className="boundary-banner">
        <strong>PVL-2H boundary:</strong> Rig manifests are sent to <code>/api/v1/rig/preview</code> before rendering. Existing <code>illustrative_geometry</code> preview files remain available as a local diagnostic fallback. Both paths still require <code>solver_mesh=false</code> in the rendered scene.
      </div>

      {error && <div className="error-panel">{error}</div>}

      {!scene ? (
        <section className="empty-state">
          <div>
            <p className="eyebrow">PVL-2H</p>
            <h2>Load a Rig manifest or an exported preview scene.</h2>
            <p>A Rig manifest uses the validated FastAPI preview path. A scene already marked as illustrative geometry is parsed locally only as a diagnostic fallback. Solver execution is not exposed by this viewer.</p>
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
