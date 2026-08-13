import type { PreviewItem, PreviewPrimitive, PreviewScene, Vec3 } from './types';

const primitives = new Set<PreviewPrimitive>([
  'box_envelope',
  'open_rectangular_loop',
  'cylinder_shell',
  'cylinder',
  'winding_envelope',
  'point',
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function parseVec3(value: unknown, label: string): Vec3 {
  if (!Array.isArray(value) || value.length !== 3) throw new Error(`${label} must be a three-value array.`);
  if (value.some((entry) => typeof entry !== 'number' || !Number.isFinite(entry))) throw new Error(`${label} must contain finite numbers.`);
  return [value[0], value[1], value[2]];
}

function requiredString(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  if (typeof value !== 'string' || value.length === 0) throw new Error(`${key} must be a non-empty string.`);
  return value;
}

function parseNumberMap(value: unknown, label: string): Record<string, number> {
  if (!isRecord(value)) throw new Error(`${label} must be an object.`);
  return Object.fromEntries(Object.entries(value).map(([key, entry]) => {
    if (typeof entry !== 'number' || !Number.isFinite(entry)) throw new Error(`${label}.${key} must be finite.`);
    return [key, entry];
  }));
}

function parseMetadata(value: unknown): Record<string, string | boolean> {
  if (!isRecord(value)) throw new Error('metadata must be an object.');
  return Object.fromEntries(Object.entries(value).map(([key, entry]) => {
    if (typeof entry !== 'string' && typeof entry !== 'boolean') throw new Error(`metadata.${key} has an unsupported value.`);
    return [key, entry];
  }));
}

function parseItem(value: unknown): PreviewItem {
  if (!isRecord(value)) throw new Error('Scene items must be objects.');
  const primitive = value.primitive;
  if (typeof primitive !== 'string' || !primitives.has(primitive as PreviewPrimitive)) throw new Error(`Unsupported primitive: ${String(primitive)}`);
  const material = value.material_id;
  if (material !== null && typeof material !== 'string') throw new Error('material_id must be a string or null.');
  return {
    component_id: requiredString(value, 'component_id'),
    primitive: primitive as PreviewPrimitive,
    material_id: material,
    center_m: parseVec3(value.center_m, 'center_m'),
    axis: value.axis === null ? null : parseVec3(value.axis, 'axis'),
    parameters_m: parseNumberMap(value.parameters_m, 'parameters_m'),
    integer_parameters: parseNumberMap(value.integer_parameters, 'integer_parameters'),
    metadata: parseMetadata(value.metadata),
    bounds_min_m: parseVec3(value.bounds_min_m, 'bounds_min_m'),
    bounds_max_m: parseVec3(value.bounds_max_m, 'bounds_max_m'),
  };
}

export function parsePreviewScene(value: unknown): PreviewScene {
  if (!isRecord(value)) throw new Error('Preview scene must be a JSON object.');
  if (value.fidelity !== 'illustrative_geometry') throw new Error('Only illustrative_geometry preview scenes are supported.');
  if (value.solver_mesh !== false) throw new Error('Solver mesh data is not accepted as preview geometry.');
  if (!Array.isArray(value.items)) throw new Error('items must be an array.');
  return {
    rig_id: requiredString(value, 'rig_id'),
    geometry_fingerprint: requiredString(value, 'geometry_fingerprint'),
    fidelity: 'illustrative_geometry',
    solver_mesh: false,
    world_bounds_min_m: parseVec3(value.world_bounds_min_m, 'world_bounds_min_m'),
    world_bounds_max_m: parseVec3(value.world_bounds_max_m, 'world_bounds_max_m'),
    items: value.items.map(parseItem),
  };
}
