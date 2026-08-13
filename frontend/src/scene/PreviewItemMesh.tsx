import { useMemo } from 'react';
import * as THREE from 'three';

import type { PreviewItem } from '../types';

interface Props {
  item: PreviewItem;
  selected: boolean;
  onSelect: (componentId: string) => void;
}

function materialColor(materialId: string | null): string {
  const id = (materialId ?? '').toLowerCase();
  if (id.includes('copper')) return '#b87333';
  if (id.includes('steel') || id.includes('iron')) return '#7c8796';
  if (id.includes('glass')) return '#73b9c6';
  if (id.includes('water')) return '#4c9bd6';
  if (id.includes('air')) return '#a8c7df';
  return '#9aa4b2';
}

function sizeFromBounds(item: PreviewItem): [number, number, number] {
  return [
    Math.max(item.bounds_max_m[0] - item.bounds_min_m[0], 0.001),
    Math.max(item.bounds_max_m[1] - item.bounds_min_m[1], 0.001),
    Math.max(item.bounds_max_m[2] - item.bounds_min_m[2], 0.001),
  ];
}

function OpenRectangularLoop({ item, selected }: { item: PreviewItem; selected: boolean }) {
  const p = item.parameters_m;
  const width = p.outer_width;
  const depth = p.outer_depth;
  const strip = p.strip_width;
  const thickness = p.thickness;
  const gap = Math.min(Math.max(p.gap_width, 0), Math.max(depth - 2 * strip, 0));
  const sideLength = Math.max(depth - 2 * strip, 0.001);
  const halfSegment = Math.max((sideLength - gap) / 2, 0.0005);
  const rightX = width / 2 - strip / 2;
  const leftX = -rightX;
  const topY = depth / 2 - strip / 2;
  const bottomY = -topY;
  const segmentOffset = gap / 2 + halfSegment / 2;
  const color = materialColor(item.material_id);

  const bar = (key: string, position: [number, number, number], scale: [number, number, number]) => (
    <mesh key={key} position={position}>
      <boxGeometry args={scale} />
      <meshStandardMaterial color={color} emissive={selected ? color : '#000000'} emissiveIntensity={selected ? 0.22 : 0} />
    </mesh>
  );

  return (
    <group>
      {bar('top', [0, topY, 0], [width, strip, thickness])}
      {bar('bottom', [0, bottomY, 0], [width, strip, thickness])}
      {bar('left', [leftX, 0, 0], [strip, sideLength, thickness])}
      {bar('right-top', [rightX, segmentOffset, 0], [strip, halfSegment, thickness])}
      {bar('right-bottom', [rightX, -segmentOffset, 0], [strip, halfSegment, thickness])}
    </group>
  );
}

export function PreviewItemMesh({ item, selected, onSelect }: Props) {
  const size = sizeFromBounds(item);
  const color = materialColor(item.material_id);
  const axisQuaternion = useMemo(() => {
    if (!item.axis) return new THREE.Quaternion();
    const axis = new THREE.Vector3(...item.axis).normalize();
    return new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), axis);
  }, [item.axis]);

  const commonMaterial = (
    <meshStandardMaterial
      color={color}
      transparent={item.primitive === 'cylinder_shell'}
      opacity={item.primitive === 'cylinder_shell' ? 0.35 : 0.82}
      wireframe={item.primitive === 'box_envelope'}
      emissive={selected ? color : '#000000'}
      emissiveIntensity={selected ? 0.25 : 0}
    />
  );

  const geometry = (() => {
    if (item.primitive === 'open_rectangular_loop') return <OpenRectangularLoop item={item} selected={selected} />;
    if (item.primitive === 'cylinder_shell' || item.primitive === 'cylinder') {
      const radius = Math.max(size[0], size[1]) / 2;
      return (
        <mesh rotation={[Math.PI / 2, 0, 0]}>
          <cylinderGeometry args={[radius, radius, size[2], 48, 1, item.primitive === 'cylinder_shell']} />
          {commonMaterial}
        </mesh>
      );
    }
    if (item.primitive === 'winding_envelope') {
      const radius = item.parameters_m.mean_radius + item.parameters_m.radial_thickness / 2;
      const height = Math.max(item.parameters_m.axial_length, 0.001);
      return (
        <mesh quaternion={axisQuaternion}>
          <cylinderGeometry args={[radius, radius, height, 64, 1, true]} />
          <meshStandardMaterial color={color} wireframe emissive={selected ? color : '#000000'} emissiveIntensity={selected ? 0.25 : 0} />
        </mesh>
      );
    }
    if (item.primitive === 'point') {
      const radius = Math.max(Math.max(...size) * 0.05, 0.005);
      return (
        <mesh>
          <sphereGeometry args={[radius, 24, 16]} />
          {commonMaterial}
        </mesh>
      );
    }
    return (
      <mesh>
        <boxGeometry args={size} />
        {commonMaterial}
      </mesh>
    );
  })();

  return (
    <group
      position={[item.center_m[0], item.center_m[1], item.center_m[2]]}
      onClick={(event) => {
        event.stopPropagation();
        onSelect(item.component_id);
      }}
    >
      {geometry}
    </group>
  );
}
