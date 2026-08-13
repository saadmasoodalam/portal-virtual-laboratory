export type Vec3 = readonly [number, number, number];

export type PreviewPrimitive =
  | 'box_envelope'
  | 'open_rectangular_loop'
  | 'cylinder_shell'
  | 'cylinder'
  | 'winding_envelope'
  | 'point';

export interface PreviewItem {
  component_id: string;
  primitive: PreviewPrimitive;
  material_id: string | null;
  center_m: Vec3;
  axis: Vec3 | null;
  parameters_m: Record<string, number>;
  integer_parameters: Record<string, number>;
  metadata: Record<string, string | boolean>;
  bounds_min_m: Vec3;
  bounds_max_m: Vec3;
}

export interface PreviewScene {
  rig_id: string;
  geometry_fingerprint: string;
  fidelity: 'illustrative_geometry';
  solver_mesh: false;
  world_bounds_min_m: Vec3;
  world_bounds_max_m: Vec3;
  items: PreviewItem[];
}
