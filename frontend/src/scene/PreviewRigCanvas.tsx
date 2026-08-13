import { OrbitControls } from '@react-three/drei';
import { Canvas } from '@react-three/fiber';
import { useMemo } from 'react';

import type { PreviewScene } from '../types';
import { PreviewItemMesh } from './PreviewItemMesh';

interface Props {
  scene: PreviewScene;
  hidden: ReadonlySet<string>;
  selected: string | null;
  onSelect: (componentId: string | null) => void;
}

export function PreviewRigCanvas({ scene, hidden, selected, onSelect }: Props) {
  const framing = useMemo(() => {
    const min = scene.world_bounds_min_m;
    const max = scene.world_bounds_max_m;
    const center: [number, number, number] = [
      (min[0] + max[0]) / 2,
      (min[1] + max[1]) / 2,
      (min[2] + max[2]) / 2,
    ];
    const span = Math.max(max[0] - min[0], max[1] - min[1], max[2] - min[2], 0.1);
    return { center, span };
  }, [scene]);

  const c = framing.center;
  const s = framing.span;

  return (
    <Canvas
      camera={{ position: [c[0] + s * 1.6, c[1] - s * 1.6, c[2] + s * 1.2], fov: 42, near: Math.max(s / 1000, 0.0001), far: s * 100 }}
      onCreated={({ camera }) => camera.up.set(0, 0, 1)}
      onPointerMissed={() => onSelect(null)}
    >
      <color attach="background" args={['#071019']} />
      <ambientLight intensity={1.4} />
      <directionalLight position={[c[0] + s, c[1] - s, c[2] + s * 2]} intensity={2.2} />
      <gridHelper
        args={[s * 3, 30, '#28465b', '#172d3c']}
        position={[c[0], c[1], scene.world_bounds_min_m[2]]}
        rotation={[Math.PI / 2, 0, 0]}
      />
      <axesHelper args={[s * 0.35]} position={c} />
      {scene.items
        .filter((item) => !hidden.has(item.component_id))
        .map((item) => (
          <PreviewItemMesh
            key={item.component_id}
            item={item}
            selected={selected === item.component_id}
            onSelect={(componentId) => onSelect(componentId)}
          />
        ))}
      <OrbitControls target={c} makeDefault />
    </Canvas>
  );
}
