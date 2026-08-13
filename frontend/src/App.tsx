import { useMemo, useState } from 'react';

import { parsePreviewScene } from './parsePreviewScene';
import { PreviewRigCanvas } from './scene/PreviewRigCanvas';
import type { PreviewScene } from './types';

function meters(value: number): string {
  if (Math.abs(value) >= 1) return `${value.toFixed(3)} m`;
  return `${(value * 1000).toFixed(1)} mm`;
}

export default function App() {
  const [scene, setScene] = useState<PreviewScene | null>(null);
  const [hidden, setHidden] = useState<Set<string>>(() => new Set());
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);

  const selectedItem = useMemo(
    () => scene?.items.find((item) => item.component_id === selected) ?? null,
    [scene, selected],
  );

  async function loadFile(file: File) {
    setError(null);
    try {
      const parsed = parsePreviewScene(JSON.parse(await file.text()));
      setScene(parsed);
      setFileName(file.name);
      setHidden(new Set());
      setSelected(null);
    } catch (caught) {
      setScene(null);
      setFileName(null);
      setSelected(null);
      setError(caught instanceof Error ? caught.message : 'Unable to read preview scene.');
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
          Load preview JSON
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
        <strong>Visualization boundary:</strong> this client accepts only PVL <code>illustrative_geometry</code> scenes with <code>solver_mesh=false</code>. It does not display a solver mesh or claim hardware fidelity.
      </div>

      {error && <div className="error-panel">{error}</div>}

      {!scene ? (
        <section className="empty-state">
          <div>
            <p className="eyebrow">PVL-2F</p>
            <h2>Load a scene exported by the PVL geometry preview pipeline.</h2>
            <p>The viewer renders the solver-neutral geometry description created downstream of the Rig manifest. No physical dimensions are invented by the browser.</p>
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
