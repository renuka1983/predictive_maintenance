import { useEffect, useMemo, useRef } from 'react';
import * as THREE from 'three';
import { useFrame, type ThreeEvent } from '@react-three/fiber';
import { useStore } from '../store';
import type { BundleBrief } from '../types';
import { bundleGeometry, bundleMaterials, dunnageGeometry, dunnageMaterial } from './textures';
import { BUNDLE_H, BUNDLE_W, DUNNAGE, levelCenterY, stackIndex } from './geometry';

const WRAPS = ['bare', 'film', 'paper', 'kraft'] as const;
const tmp = new THREE.Object3D();

/** One bundle mesh with dunnage, long axis along local x. */
export function BundleMesh({ wrap, len, highlight = false }: { wrap: string; len: number; highlight?: boolean }) {
  const mats = bundleMaterials((wrap as any) ?? 'bare');
  const L = len / 1000;
  return (
    <group>
      <mesh geometry={bundleGeometry} material={mats} scale={[L, BUNDLE_H, BUNDLE_W]} position={[0, 0, 0]} castShadow />
      <mesh geometry={dunnageGeometry} material={dunnageMaterial} position={[-L * 0.33, -BUNDLE_H / 2 - DUNNAGE / 2, 0]} />
      <mesh geometry={dunnageGeometry} material={dunnageMaterial} position={[L * 0.33, -BUNDLE_H / 2 - DUNNAGE / 2, 0]} />
      {highlight && <Highlight len={len} />}
    </group>
  );
}

function Highlight({ len, color = '#fde047' }: { len: number; color?: string }) {
  const ref = useRef<THREE.Mesh>(null);
  useFrame(({ clock }) => {
    if (ref.current) (ref.current.material as THREE.MeshBasicMaterial).opacity = 0.35 + 0.25 * Math.sin(clock.elapsedTime * 6);
  });
  return (
    <mesh ref={ref} scale={[len / 1000 + 0.25, BUNDLE_H + 0.2, BUNDLE_W + 0.25]}>
      <boxGeometry />
      <meshBasicMaterial color={color} transparent opacity={0.5} depthWrite={false} />
    </mesh>
  );
}

function WrapGroup({ wrap, items, stacks, onPick }: {
  wrap: string; items: BundleBrief[]; stacks: ReturnType<typeof stackIndex>; onPick: (b: BundleBrief, e: ThreeEvent<MouseEvent>) => void;
}) {
  const ref = useRef<THREE.InstancedMesh>(null);
  const dref = useRef<THREE.InstancedMesh>(null);
  const cap = Math.max(16, Math.ceil(items.length * 1.5 / 16) * 16);
  useEffect(() => {
    const m = ref.current, d = dref.current;
    if (!m || !d) return;
    items.forEach((b, i) => {
      const loc = b.loc as { s: string; l: number };
      const st = stacks[loc.s];
      const L = b.len / 1000;
      const y = levelCenterY(loc.l);
      tmp.position.set(st.x, y, st.z);
      tmp.rotation.set(0, st.yaw, 0);
      tmp.scale.set(L, BUNDLE_H, BUNDLE_W);
      tmp.updateMatrix();
      m.setMatrixAt(i, tmp.matrix);
      for (let k = 0; k < 2; k++) {
        tmp.position.set(st.x + (k ? 1 : -1) * L * 0.33, y - BUNDLE_H / 2 - DUNNAGE / 2, st.z);
        tmp.scale.set(1, 1, 1);
        tmp.updateMatrix();
        d.setMatrixAt(i * 2 + k, tmp.matrix);
      }
    });
    m.count = items.length;
    d.count = items.length * 2;
    m.instanceMatrix.needsUpdate = true;
    d.instanceMatrix.needsUpdate = true;
    m.computeBoundingSphere();
  }, [items, stacks]);
  return (
    <group>
      <instancedMesh key={`b${cap}`} ref={ref} args={[bundleGeometry, bundleMaterials(wrap as any), cap]} castShadow receiveShadow
        onClick={(e) => { e.stopPropagation(); if (e.instanceId !== undefined && items[e.instanceId]) onPick(items[e.instanceId], e); }}
        onPointerOver={(e) => { e.stopPropagation(); document.body.style.cursor = 'pointer'; }}
        onPointerOut={() => { document.body.style.cursor = 'default'; }} />
      <instancedMesh key={`d${cap}`} ref={dref} args={[dunnageGeometry, dunnageMaterial, cap * 2]} receiveShadow />
    </group>
  );
}

export function StackBundles() {
  const layout = useStore((s) => s.layout);
  const bundles = useStore((s) => s.bundles);
  const selection = useStore((s) => s.selection);
  const highlightOrder = useStore((s) => s.highlightOrder);
  const select = useStore((s) => s.select);
  const stacks = useMemo(() => (layout ? stackIndex(layout) : {}), [layout]);
  const groups = useMemo(() => {
    const g: Record<string, BundleBrief[]> = { bare: [], film: [], paper: [], kraft: [] };
    for (const b of bundles) if (b.loc.k === 's' && stacks[(b.loc as any).s]) (g[b.w] ?? g.bare).push(b);
    return g;
  }, [bundles, stacks]);
  const highlighted = useMemo(() => bundles.filter((b) => b.loc.k === 's' &&
    ((selection?.kind === 'bundle' && selection.id === b.id) || (highlightOrder && b.so === highlightOrder))), [bundles, selection, highlightOrder]);
  if (!layout) return null;
  return (
    <group>
      {WRAPS.map((w) => <WrapGroup key={w} wrap={w} items={groups[w]} stacks={stacks} onPick={(b) => select({ kind: 'bundle', id: b.id })} />)}
      {highlighted.map((b) => {
        const loc = b.loc as { s: string; l: number };
        const st = stacks[loc.s];
        const sel = selection?.kind === 'bundle' && selection.id === b.id;
        return (
          <group key={b.id} position={[st.x, levelCenterY(loc.l), st.z]}>
            <Highlight len={b.len} color={sel ? '#fde047' : '#f472b6'} />
          </group>
        );
      })}
      {selection?.kind === 'stack' && stacks[selection.id] && (
        <mesh position={[stacks[selection.id].x, 1.6, stacks[selection.id].z]}>
          <boxGeometry args={[6.8, 3.2, 1.8]} />
          <meshBasicMaterial color="#38bdf8" transparent opacity={0.15} depthWrite={false} />
        </mesh>
      )}
    </group>
  );
}
