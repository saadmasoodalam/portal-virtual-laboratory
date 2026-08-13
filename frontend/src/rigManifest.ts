export type MeasurementStatus = 'unknown' | 'illustrative' | 'measured' | 'supplier';

export interface MeasurementEntry {
  path: readonly string[];
  displayPath: string;
  valueKey: 'value_m' | 'value';
  value: number | null;
  status: MeasurementStatus;
  sourceNote: string;
  requiredForSolver: boolean;
}

const measurementStatuses = new Set<MeasurementStatus>([
  'unknown',
  'illustrative',
  'measured',
  'supplier',
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isMeasurementRecord(value: unknown): value is Record<string, unknown> {
  if (!isRecord(value)) return false;
  if (typeof value.status !== 'string' || !measurementStatuses.has(value.status as MeasurementStatus)) return false;
  if (typeof value.source_note !== 'string') return false;
  if (typeof value.required_for_solver !== 'boolean') return false;
  return Object.hasOwn(value, 'value_m') || Object.hasOwn(value, 'value');
}

function formatPath(parts: readonly string[]): string {
  return parts.join('.');
}

function collect(value: unknown, path: readonly string[], result: MeasurementEntry[]): void {
  if (isMeasurementRecord(value)) {
    const valueKey = Object.hasOwn(value, 'value_m') ? 'value_m' : 'value';
    const rawValue = value[valueKey];
    result.push({
      path,
      displayPath: formatPath(path),
      valueKey,
      value: typeof rawValue === 'number' && Number.isFinite(rawValue) ? rawValue : null,
      status: value.status as MeasurementStatus,
      sourceNote: value.source_note as string,
      requiredForSolver: value.required_for_solver as boolean,
    });
    return;
  }

  if (Array.isArray(value)) {
    value.forEach((child, index) => collect(child, [...path, String(index)], result));
    return;
  }

  if (isRecord(value)) {
    Object.entries(value).forEach(([key, child]) => collect(child, [...path, key], result));
  }
}

export function listMeasurements(manifest: unknown): MeasurementEntry[] {
  const result: MeasurementEntry[] = [];
  collect(manifest, [], result);
  return result;
}

function cloneManifest(manifest: Record<string, unknown>): Record<string, unknown> {
  return structuredClone(manifest) as Record<string, unknown>;
}

function getMutableRecord(root: Record<string, unknown>, path: readonly string[]): Record<string, unknown> {
  let current: unknown = root;
  for (const part of path) {
    if (Array.isArray(current)) {
      const index = Number(part);
      current = current[index];
    } else if (isRecord(current)) {
      current = current[part];
    } else {
      throw new Error(`Rig manifest path ${formatPath(path)} is not editable.`);
    }
  }
  if (!isRecord(current)) throw new Error(`Rig manifest path ${formatPath(path)} is not an object.`);
  return current;
}

export function updateMeasurement(
  manifest: Record<string, unknown>,
  entry: MeasurementEntry,
  patch: Partial<Pick<MeasurementEntry, 'value' | 'status' | 'sourceNote'>>,
): Record<string, unknown> {
  const next = cloneManifest(manifest);
  const target = getMutableRecord(next, entry.path);

  if (patch.status !== undefined) {
    target.status = patch.status;
    if (patch.status === 'unknown') target[entry.valueKey] = null;
  }
  if (patch.value !== undefined) target[entry.valueKey] = patch.value;
  if (patch.sourceNote !== undefined) target.source_note = patch.sourceNote;
  return next;
}

export interface MeasurementSummary {
  total: number;
  required: number;
  missingRequired: number;
  illustrative: number;
  hardwareFidelity: number;
}

export function summarizeMeasurements(manifest: unknown): MeasurementSummary {
  const entries = listMeasurements(manifest);
  return {
    total: entries.length,
    required: entries.filter((entry) => entry.requiredForSolver).length,
    missingRequired: entries.filter(
      (entry) => entry.requiredForSolver && (entry.status === 'unknown' || entry.value === null),
    ).length,
    illustrative: entries.filter((entry) => entry.status === 'illustrative').length,
    hardwareFidelity: entries.filter(
      (entry) => entry.status === 'measured' || entry.status === 'supplier',
    ).length,
  };
}

export function topLevelGroup(entry: MeasurementEntry): string {
  return entry.path[0] ?? 'rig';
}

export function measurementLabel(entry: MeasurementEntry): string {
  const leaf = entry.path[entry.path.length - 1] ?? 'measurement';
  return leaf.replaceAll('_', ' ');
}
