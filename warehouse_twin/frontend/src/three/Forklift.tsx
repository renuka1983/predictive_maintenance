import { useRef } from 'react';
import * as THREE from 'three';
import { useFrame } from '@react-three/fiber';
import { Html } from '@react-three/drei';
import { liveIndex, useStore } from '../store';
import type { SimEvent } from '../types';
import { BundleMesh } from './Bundles';
import { BUNDLE_H, ROLE_COLOR, lerpAngle } from './geometry';

function M({ color, metal = 0.2, rough = 0.6, emissive, ei = 0, opacity = 1 }: { color: string; metal?: number; rough?: number; emissive?: string; ei?: number; opacity?: number }) {
  return <meshStandardMaterial color={color} metalness={metal} roughness={rough} emissive={emissive ?? '#000000'} emissiveIntensity={ei}
    transparent={opacity < 1} opacity={opacity} />;
}

/** Procedural long-load forklift. Local +x is forward; forks/carriage are a child group moved in y. */
export function ForkliftBody({ color, forksRef, beaconRef, opacity = 1, rfid = false }: {
  color: string; forksRef?: React.RefObject<THREE.Group | null>; beaconRef?: React.RefObject<THREE.Mesh | null>; opacity?: number; rfid?: boolean;
}) {
  const wheel = (x: number, z: number, r = 0.32) => (
    <mesh key={`${x}${z}`} position={[x, r, z]} rotation={[Math.PI / 2, 0, 0]} castShadow>
      <cylinderGeometry args={[r, r, 0.28, 16]} />
      <M color="#111827" rough={0.9} opacity={opacity} />
    </mesh>
  );
  return (
    <group>
      {/* chassis + counterweight */}
      <mesh position={[0.05, 0.62, 0]} castShadow><boxGeometry args={[2.2, 0.75, 1.35]} /><M color={color} opacity={opacity} /></mesh>
      <mesh position={[-1.0, 0.75, 0]} castShadow><boxGeometry args={[0.5, 1.0, 1.4]} /><M color="#1f2937" metal={0.5} opacity={opacity} /></mesh>
      <mesh position={[-0.2, 1.15, 0]}><boxGeometry args={[0.55, 0.35, 0.6]} /><M color="#111827" opacity={opacity} /></mesh>
      {/* overhead guard */}
      {[[0.55, 0.6], [0.55, -0.6], [-0.75, 0.6], [-0.75, -0.6]].map(([x, z]) => (
        <mesh key={`${x}${z}`} position={[x, 1.65, z]}><boxGeometry args={[0.07, 1.3, 0.07]} /><M color="#0f172a" metal={0.6} opacity={opacity} /></mesh>
      ))}
      <mesh position={[-0.1, 2.32, 0]} castShadow><boxGeometry args={[1.45, 0.07, 1.32]} /><M color="#0f172a" metal={0.6} opacity={opacity} /></mesh>
      {/* operator */}
      <mesh position={[-0.25, 1.55, 0]}><capsuleGeometry args={[0.2, 0.4, 4, 8]} /><M color="#f97316" opacity={opacity} /></mesh>
      <mesh position={[-0.25, 2.0, 0]}><sphereGeometry args={[0.15, 12, 12]} /><M color="#facc15" opacity={opacity} /></mesh>
      {/* mast */}
      {[0.45, -0.45].map((z) => (
        <mesh key={z} position={[1.22, 1.6, z]} castShadow><boxGeometry args={[0.12, 3.2, 0.12]} /><M color="#374151" metal={0.7} opacity={opacity} /></mesh>
      ))}
      <mesh position={[1.22, 3.15, 0]}><boxGeometry args={[0.12, 0.1, 1.0]} /><M color="#374151" metal={0.7} opacity={opacity} /></mesh>
      {/* beacon */}
      <mesh ref={beaconRef} position={[-0.75, 2.45, 0]}><cylinderGeometry args={[0.09, 0.09, 0.14, 12]} /><M color="#f59e0b" emissive="#f59e0b" ei={1.5} opacity={opacity} /></mesh>
      {wheel(0.75, 0.62)}{wheel(0.75, -0.62)}{wheel(-0.75, 0.6, 0.28)}{wheel(-0.75, -0.6, 0.28)}
      {/* carriage + forks */}
      <group ref={forksRef} position={[0, 0.12, 0]}>
        <mesh position={[1.32, 0.45, 0]}><boxGeometry args={[0.08, 0.9, 1.25]} /><M color="#1f2937" metal={0.6} opacity={opacity} /></mesh>
        {[0.4, -0.4].map((z) => (
          <mesh key={z} position={[1.95, 0.03, z]} castShadow><boxGeometry args={[1.25, 0.06, 0.13]} /><M color="#4b5563" metal={0.8} rough={0.3} opacity={opacity} /></mesh>
        ))}
        {rfid && (
          <mesh position={[2.6, 0.3, 0]} rotation={[0, 0, -Math.PI / 2]}>
            <coneGeometry args={[0.9, 1.6, 20, 1, true]} />
            <meshBasicMaterial color="#22d3ee" transparent opacity={0.12} side={THREE.DoubleSide} depthWrite={false} />
          </mesh>
        )}
      </group>
    </group>
  );
}

export function Forklift({ id }: { id: string }) {
  const g = useRef<THREE.Group>(null);
  const forks = useRef<THREE.Group>(null);
  const beacon = useRef<THREE.Mesh>(null);
  const init = useRef(true);
  const role = useStore((s) => s.sim?.forklifts.find((f) => f.id === id)?.role ?? 'PUTAWAY');
  const load = useStore((s) => s.sim?.forklifts.find((f) => f.id === id)?.load ?? null);
  const state = useStore((s) => s.sim?.forklifts.find((f) => f.id === id)?.state ?? '');
  const yieldTo = useStore((s) => s.sim?.forklifts.find((f) => f.id === id)?.yieldTo ?? null);
  const loadBundle = useStore((s) => (load ? s.bundleIndex[load] : undefined));
  const selected = useStore((s) => s.selection?.kind === 'forklift' && s.selection.id === id);
  const select = useStore((s) => s.select);
  const rfid = useStore((s) => s.toggles.rfid);
  const labels = useStore((s) => s.toggles.labels);
  const color = ROLE_COLOR[role];

  useFrame(({ clock }, dt) => {
    const f = liveIndex.forklift(id);
    if (!f || !g.current || !forks.current) return;
    const k = init.current ? 1 : 1 - Math.exp(-dt * 9);
    init.current = false;
    g.current.position.x += (f.x - g.current.position.x) * k;
    g.current.position.z += (f.z - g.current.position.z) * k;
    g.current.rotation.y = lerpAngle(g.current.rotation.y, f.h, k);
    forks.current.position.y += (f.fork - forks.current.position.y) * k;
    if (beacon.current) beacon.current.visible = f.state !== 'IDLE' && Math.sin(clock.elapsedTime * 10) > 0;
  });

  return (
    <group ref={g} onClick={(e) => { e.stopPropagation(); select({ kind: 'forklift', id }); }}
      onPointerOver={() => (document.body.style.cursor = 'pointer')} onPointerOut={() => (document.body.style.cursor = 'default')}>
      <ForkliftBody color={color} forksRef={forks} beaconRef={beacon} rfid={rfid} />
      <ForkLoad forks={forks} bundle={loadBundle} />
      {selected && (
        <mesh position={[0, 0.05, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[2.2, 2.6, 40]} />
          <meshBasicMaterial color="#fde047" transparent opacity={0.8} />
        </mesh>
      )}
      <CaptureCard id={id} />
      {labels && (
        <Html zIndexRange={[3, 0]} position={[0, 3.6, 0]} center style={{ pointerEvents: 'none' }}>
          <div style={{ background: yieldTo ? '#b45309' : color, color: 'white', padding: '1px 6px', borderRadius: 4, fontSize: 12, fontWeight: 700,
            fontFamily: 'Roboto, sans-serif', whiteSpace: 'nowrap', boxShadow: '0 1px 4px rgba(0,0,0,.5)', opacity: 0.95 }}>
            {id}{yieldTo ? ` · yielding to ${yieldTo}` : state && state !== 'IDLE' ? ` · ${state.replace('_', ' ').toLowerCase()}` : ''}
          </div>
        </Html>
      )}
    </group>
  );
}

/** Renders the carried bundle so that it follows the animated fork carriage height. */
function ForkLoad({ forks, bundle }: { forks: React.RefObject<THREE.Group | null>; bundle?: { w: string; len: number } }) {
  const ref = useRef<THREE.Group>(null);
  useFrame(() => {
    if (ref.current && forks.current) ref.current.position.y = forks.current.position.y + 0.06 + BUNDLE_H / 2;
  });
  if (!bundle) return null;
  return (
    <group ref={ref} position={[2.0, 0.5, 0]} rotation={[0, Math.PI / 2, 0]}>
      <BundleMesh wrap={bundle.w} len={bundle.len} />
    </group>
  );
}

const CARD_SECONDS = 7; // simulation seconds a capture card stays up (it freezes while paused)

/** Pop-up showing what the forklift captured at the stack face and what it posted to Oracle. */
function CaptureCard({ id }: { id: string }) {
  const ev = useStore((s) => {
    for (let i = s.events.length - 1, n = 0; i >= 0 && n < 120; i--, n++) {
      const e = s.events[i];
      if (e.refs?.forklift === id && (e.type === 'BUNDLE_PICKED' || e.type === 'BUNDLE_PLACED')) return e;
    }
    return null;
  }) as SimEvent | null;
  const t = useStore((s) => s.sim?.t ?? 0);
  if (!ev || t - ev.t > CARD_SECONDS || t < ev.t - 1) return null;
  const placed = ev.type === 'BUNDLE_PLACED';
  const r = ev.refs;
  const row = (k: string, v: string, c = '#e2e8f0') => (
    <div style={{ display: 'flex', gap: 6 }}>
      <span style={{ color: '#94a3b8', width: 62, flexShrink: 0 }}>{k}</span>
      <span style={{ color: c, fontFamily: 'ui-monospace, Menlo, monospace' }}>{v}</span>
    </div>
  );
  return (
    <Html zIndexRange={[4, 0]} position={[0, 5.4, 0]} center style={{ pointerEvents: 'none' }}>
      <div style={{ background: 'rgba(15,23,42,.94)', border: `2px solid ${placed ? '#22c55e' : '#22d3ee'}`, borderRadius: 8,
        padding: '6px 9px', fontSize: 11.5, fontFamily: 'Roboto, sans-serif', color: '#e2e8f0', whiteSpace: 'nowrap',
        boxShadow: '0 4px 14px rgba(0,0,0,.5)' }}>
        <div style={{ fontWeight: 800, color: placed ? '#4ade80' : '#67e8f9', marginBottom: 2, letterSpacing: 0.3 }}>
          {id} · {placed ? 'PLACEMENT CONFIRMED' : 'PICK-UP SCAN'} · {String(r.task_type ?? '').toLowerCase()}
        </div>
        {row('RFID EPC', `${String(r.epc ?? '').slice(0, 6)}…${String(r.epc ?? '').slice(-8)}  read OK`, '#67e8f9')}
        {row('Barcode', String(r.barcode ?? ''))}
        {row(placed ? 'Location' : 'From', String(r.location ?? ''), '#fde68a')}
        {placed && r.oracle && row('Oracle', `${r.oracle}  posted`, '#c4b5fd')}
      </div>
    </Html>
  );
}
