import type { MaterialCatalog, MaterialCatalogItem, MaterialCategory } from './api';

interface RigConfigurationEditorProps {
  manifest: Record<string, unknown>;
  catalog: MaterialCatalog;
  onChange: (manifest: Record<string, unknown>) => void;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function getPath(root: Record<string, unknown>, path: string[]): unknown {
  let current: unknown = root;
  for (const key of path) {
    if (!isRecord(current)) return undefined;
    current = current[key];
  }
  return current;
}

function setPath(root: Record<string, unknown>, path: string[], value: unknown): Record<string, unknown> {
  const next = structuredClone(root);
  let current: Record<string, unknown> = next;
  path.slice(0, -1).forEach((key) => {
    const child = current[key];
    if (!isRecord(child)) throw new Error(`Rig manifest path ${path.join('.')} is invalid.`);
    current = child;
  });
  current[path[path.length - 1]] = value;
  return next;
}

function selectMaterials(catalog: MaterialCatalog, categories: MaterialCategory[]): MaterialCatalogItem[] {
  return catalog.materials.filter((item) => categories.includes(item.category));
}

interface MaterialFieldProps {
  label: string;
  path: string[];
  categories: MaterialCategory[];
  manifest: Record<string, unknown>;
  catalog: MaterialCatalog;
  onChange: (manifest: Record<string, unknown>) => void;
}

function MaterialField({ label, path, categories, manifest, catalog, onChange }: MaterialFieldProps) {
  const current = String(getPath(manifest, path) ?? '');
  const choices = selectMaterials(catalog, categories);
  const selected = catalog.materials.find((item) => item.material_id === current);

  return (
    <label className="config-field">
      <span>{label}</span>
      <select value={current} onChange={(event) => onChange(setPath(manifest, path, event.currentTarget.value))}>
        {choices.map((item) => (
          <option key={item.material_id} value={item.material_id}>{item.display_name}</option>
        ))}
      </select>
      {selected && (
        <small>
          {selected.provenance_status} · {selected.model_kind}
          {selected.hardware_fidelity_data ? ' · hardware-fidelity data' : ' · baseline data'}
        </small>
      )}
      {selected?.solver_warning && <small className="config-warning">{selected.solver_warning}</small>}
    </label>
  );
}

export function RigConfigurationEditor({ manifest, catalog, onChange }: RigConfigurationEditorProps) {
  const openLoop = Boolean(getPath(manifest, ['copper_boundary', 'baseline_open_loop']));
  const isolated = Boolean(getPath(manifest, ['copper_boundary', 'electrically_isolated_from_frame']));

  return (
    <section className="configuration-panel">
      <div className="measurement-group-heading">
        <div>
          <p className="eyebrow">PVL-2J controlled configuration</p>
          <h3>Materials & boundary state</h3>
        </div>
        <span>library {catalog.library_version}</span>
      </div>

      <div className="configuration-grid">
        <MaterialField label="Ambient medium" path={['ambient_material_id']} categories={['gas']} manifest={manifest} catalog={catalog} onChange={onChange} />
        <MaterialField label="Steel / iron frame" path={['frame', 'material_id']} categories={['metal']} manifest={manifest} catalog={catalog} onChange={onChange} />
        <MaterialField label="Copper boundary" path={['copper_boundary', 'material_id']} categories={['metal']} manifest={manifest} catalog={catalog} onChange={onChange} />
        <MaterialField label="Sample vessel wall" path={['sample_chamber', 'wall_material_id']} categories={['glass']} manifest={manifest} catalog={catalog} onChange={onChange} />
        <MaterialField label="Sample chamber medium" path={['sample_chamber', 'medium_material_id']} categories={['gas', 'liquid']} manifest={manifest} catalog={catalog} onChange={onChange} />
        <MaterialField label="Coil A conductor" path={['coil_a', 'conductor_material_id']} categories={['metal']} manifest={manifest} catalog={catalog} onChange={onChange} />
        <MaterialField label="Coil B conductor" path={['coil_b', 'conductor_material_id']} categories={['metal']} manifest={manifest} catalog={catalog} onChange={onChange} />
      </div>

      <div className="boundary-controls">
        <label className="toggle-card">
          <input
            type="checkbox"
            checked={openLoop}
            onChange={(event) => onChange(setPath(manifest, ['copper_boundary', 'baseline_open_loop'], event.currentTarget.checked))}
          />
          <span><strong>Copper boundary open loop</strong><small>Rig v1 baseline is open/gapped. Closed-loop tests must be explicitly selected.</small></span>
        </label>
        <label className="toggle-card">
          <input
            type="checkbox"
            checked={isolated}
            onChange={(event) => onChange(setPath(manifest, ['copper_boundary', 'electrically_isolated_from_frame'], event.currentTarget.checked))}
          />
          <span><strong>Copper electrically isolated from frame</strong><small>Keep enabled for the documented Rig v1 baseline unless intentionally testing another controlled configuration.</small></span>
        </label>
      </div>

      <div className="editor-notice">
        Selecting distilled water or 0.9% saline changes only the declared chamber medium. Saline remains a comparison arm. These controls still generate preview-only geometry; they do not start a FEM solver.
      </div>
    </section>
  );
}
