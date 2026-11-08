import { useRef } from 'react';
import * as THREE from 'three';
import { useFrame } from '@react-three/fiber';
import { Html } from '@react-three/drei';
import { liveIndex, useStore } from '../store';
import { BundleMesh } from './Bundles';
import { levelCenterY, lerpAngle } from './geometry';

export function Truck({ id }: { id: string }) {
  const g = useRef<THREE.Group>(null);
  const init = useRef(true);
  const layout = useStore((s) => s.layout);
  const bundles = useStore((s) => s.bundles);
  const plate = useStore((s) => s.sim?.trucks.find((t) => t.id === id)?.plate);
  const state = useStore((s) => s.sim?.trucks.find((t) => t.id === id)?.state);
  const select = useStore((s) => s.select);
  const labels = useStore((s) => s.toggles.labels);
  useFrame((_, dt) => {
    const t = liveIndex.truck(id);
    if (!t || !g.current) return;
    const k = init.current ? 1 : 1 - Math.exp(-dt * 6);
    init.current = false;
    g.current.position.x += (t.x - g.current.position.x) * k;
    g.current.position.z += (t.z - g.current.position.z) * k;
    g.current.rotation.y = lerpAngle(g.current.rotation.y, t.h, k);
  });
  if (!layout) return null;
  const bed = layout.truck.bed;
  const loads = bundles.filter((b) => b.loc.k === 't' && (b.loc as any).t === id);
  const wheels = [];
  for (const x of [-5.6, -4.4, -3.2, 4.6, 7.0, 8.3]) for (const z of [-1.05, 1.05]) wheels.push([x, z]);
  return (
    <group ref={g} onClick={(e) => { e.stopPropagation(); select({ kind: 'truck', id }); }}>
      {/* trailer deck */}
      <mesh position={[0, bed - 0.12, 0]} castShadow receiveShadow><boxGeometry args={[13.6, 0.25, 2.5]} /><meshStandardMaterial color="#334155" metalness={0.5} /></mesh>
      <mesh position={[0, bed - 0.45, 0]}><boxGeometry args={[13.2, 0.35, 0.6]} /><meshStandardMaterial color="#1e293b" /></mesh>
      {[-6.7, 6.7].map((x) => <mesh key={x} position={[x, bed + 0.6, 0]}><boxGeometry args={[0.15, 1.2, 2.5]} /><meshStandardMaterial color="#475569" /></mesh>)}
      {[-4.5, -1.5, 1.5, 4.5].map((x) => [1.2, -1.2].map((z) => (
        <mesh key={`${x}${z}`} position={[x, bed + 0.5, z]}><boxGeometry args={[0.1, 1.0, 0.1]} /><meshStandardMaterial color="#facc15" /></mesh>
      )))}
      {/* tractor */}
      <mesh position={[8.6, 1.9, 0]} castShadow><boxGeometry args={[2.3, 2.6, 2.5]} /><meshStandardMaterial color="#b91c1c" metalness={0.3} roughness={0.4} /></mesh>
      <mesh position={[9.76, 2.4, 0]}><boxGeometry args={[0.05, 1.0, 2.2]} /><meshStandardMaterial color="#0f172a" metalness={0.9} roughness={0.1} /></mesh>
      <mesh position={[7.5, 0.9, 0]}><boxGeometry args={[3.6, 0.6, 1.4]} /><meshStandardMaterial color="#111827" /></mesh>
      {wheels.map(([x, z], i) => (
        <mesh key={i} position={[x, 0.5, z]} rotation={[Math.PI / 2, 0, 0]} castShadow>
          <cylinderGeometry args={[0.5, 0.5, 0.35, 18]} /><meshStandardMaterial color="#0b0f14" roughness={0.9} />
        </mesh>
      ))}
      {loads.map((b) => {
        const loc = b.loc as { c: number; l: number };
        return (
          <group key={b.id} position={[layout.truck.cols[loc.c], levelCenterY(loc.l, bed), 0]}>
            <BundleMesh wrap={b.w} len={b.len} />
          </group>
        );
      })}
      {labels && (
        <Html zIndexRange={[3, 0]} position={[8.6, 4.2, 0]} center style={{ pointerEvents: 'none' }}>
          <div style={{ background: '#7f1d1d', color: 'white', padding: '1px 6px', borderRadius: 4, fontSize: 12, fontWeight: 700,
            fontFamily: 'Roboto, sans-serif', whiteSpace: 'nowrap' }}>{plate} · {state?.toLowerCase().replace('_', ' ')}</div>
        </Html>
      )}
    </group>
  );
}

export function Trucks() {
  const ids = useStore((s) => (s.sim?.trucks ?? []).map((t) => t.id).join(','));
  return <>{ids.split(',').filter(Boolean).map((id) => <Truck key={id} id={id} />)}</>;
}
