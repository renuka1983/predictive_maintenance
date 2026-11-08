import { useMemo, useRef } from 'react';
import * as THREE from 'three';
import { useFrame } from '@react-three/fiber';
import { Html, Line } from '@react-three/drei';
import { useStore } from '../store';
import { ForkliftBody } from './Forklift';
import { ROLE_COLOR, stackIndex } from './geometry';

export function Routes() {
  const forklifts = useStore((s) => s.sim?.forklifts);
  const show = useStore((s) => s.toggles.routes);
  if (!show || !forklifts) return null;
  return (
    <group>
      {forklifts.filter((f) => f.route.length > 1).map((f) => (
        <group key={f.id}>
          <Line points={f.route.map(([x, z]) => [x, 0.12, z] as [number, number, number])} color={ROLE_COLOR[f.role]}
            lineWidth={3} dashed dashSize={0.8} gapSize={0.5} transparent opacity={0.9} />
          {f.dest && (
            <mesh position={[f.dest.x, 0.08, f.dest.z]} rotation={[-Math.PI / 2, 0, 0]}>
              <ringGeometry args={[0.5, 0.85, 24]} />
              <meshBasicMaterial color={ROLE_COLOR[f.role]} />
            </mesh>
          )}
        </group>
      ))}
    </group>
  );
}

export function UwbLinks() {
  const forklifts = useStore((s) => s.sim?.forklifts);
  const anchors = useStore((s) => s.layout?.anchors);
  const show = useStore((s) => s.toggles.uwb);
  if (!show || !forklifts || !anchors) return null;
  return (
    <group>
      {forklifts.map((f) => {
        const near = anchors.filter((a) => a.warehouse === f.warehouse)
          .map((a) => ({ a, d: Math.hypot(a.x - f.x, a.z - f.z) })).sort((p, q) => p.d - q.d).slice(0, 4);
        return (
          <group key={f.id}>
            {near.map(({ a }) => (
              <Line key={a.id} points={[[a.x, a.y + 0.2, a.z], [f.x, 2.4, f.z]]} color="#fb923c" lineWidth={1} transparent opacity={0.55} />
            ))}
            <mesh position={[f.x, 0.06, f.z]} rotation={[-Math.PI / 2, 0, 0]}>
              <ringGeometry args={[2.8, 2.8 + f.uwbErr * 6, 32]} />
              <meshBasicMaterial color="#fb923c" transparent opacity={0.5} />
            </mesh>
          </group>
        );
      })}
    </group>
  );
}

function PulseRing({ x, z, born, color, big }: { x: number; z: number; born: number; color: string; big?: boolean }) {
  const ref = useRef<THREE.Mesh>(null);
  useFrame(() => {
    if (!ref.current) return;
    const a = (performance.now() - born) / 1600;
    ref.current.visible = a < 1;
    const s = (big ? 9 : 3) * (0.2 + a);
    ref.current.scale.set(s, s, s);
    (ref.current.material as THREE.MeshBasicMaterial).opacity = Math.max(0, 0.8 * (1 - a));
  });
  return (
    <mesh ref={ref} position={[x, big ? 3 : 1.2, z]} rotation={[-Math.PI / 2, 0, 0]}>
      <ringGeometry args={[0.8, 1, 40]} />
      <meshBasicMaterial color={color} transparent depthWrite={false} side={THREE.DoubleSide} />
    </mesh>
  );
}

export function RfidPulses() {
  const pulses = useStore((s) => s.pulses);
  const show = useStore((s) => s.toggles.rfid);
  if (!show) return null;
  return <group>{pulses.map((p) => <PulseRing key={p.id} {...p} />)}</group>;
}

export function ReplayGhost() {
  const replay = useStore((s) => s.replay);
  const setReplay = useStore((s) => s.setReplay);
  const g = useRef<THREE.Group>(null);
  const [cum, total] = useMemo(() => {
    if (!replay) return [[0], 0];
    const c = [0];
    for (let i = 1; i < replay.path.length; i++) {
      const [ax, az] = replay.path[i - 1], [bx, bz] = replay.path[i];
      c.push(c[i - 1] + Math.hypot(bx - ax, bz - az));
    }
    return [c, c[c.length - 1]];
  }, [replay]);
  const playSeconds = replay ? Math.max(6, Math.min(18, replay.duration_s / 4)) : 1;
  useFrame(() => {
    if (!replay || !g.current || total <= 0) return;
    const a = Math.min(1, (performance.now() - (replay.startedAt ?? 0)) / 1000 / playSeconds);
    const d = a * total;
    let i = 1;
    while (i < cum.length - 1 && cum[i] < d) i++;
    const [ax, az] = replay.path[i - 1], [bx, bz] = replay.path[i];
    const seg = cum[i] - cum[i - 1] || 1;
    const u = Math.min(1, Math.max(0, (d - cum[i - 1]) / seg));
    g.current.position.set(ax + (bx - ax) * u, 0, az + (bz - az) * u);
    if (Math.hypot(bx - ax, bz - az) > 0.3) g.current.rotation.y = Math.atan2(-(bz - az), bx - ax);
    if (a >= 1 && performance.now() - (replay.startedAt ?? 0) > (playSeconds + 4) * 1000) setReplay(null);
  });
  if (!replay || replay.path.length < 2) return null;
  const pts = replay.path.map(([x, z]) => [x, 0.2, z] as [number, number, number]);
  const [sx, sz] = replay.path[0];
  const [ex, ez] = replay.path[replay.path.length - 1];
  return (
    <group>
      <Line points={pts} color="#e879f9" lineWidth={4} transparent opacity={0.85} />
      <group ref={g}><ForkliftBody color="#c026d3" opacity={0.55} /></group>
      <Html zIndexRange={[3, 0]} position={[sx, 3, sz]} center style={{ pointerEvents: 'none' }}>
        <div style={tag}>REPLAY start · {replay.task.from}</div>
      </Html>
      <Html zIndexRange={[3, 0]} position={[ex, 3, ez]} center style={{ pointerEvents: 'none' }}>
        <div style={tag}>end · {replay.task.to}</div>
      </Html>
    </group>
  );
}
const tag: React.CSSProperties = { background: '#a21caf', color: 'white', padding: '1px 6px', borderRadius: 4, fontSize: 11,
  fontFamily: 'Roboto, sans-serif', whiteSpace: 'nowrap' };

/** Invisible clickable footprints so an empty or partially filled stack can be selected. */
export function StackPads() {
  const layout = useStore((s) => s.layout);
  const select = useStore((s) => s.select);
  const stacks = useMemo(() => (layout ? Object.values(stackIndex(layout)) : []), [layout]);
  return (
    <group>
      {stacks.map((s) => (
        <mesh key={s.id} position={[s.x, 0.03, s.z]} rotation={[-Math.PI / 2, 0, 0]}
          onClick={(e) => { e.stopPropagation(); select({ kind: 'stack', id: s.id }); }}>
          <planeGeometry args={[6.2, 1.4]} />
          <meshBasicMaterial color={s.kind === 'STAGING' ? '#a855f7' : s.kind === 'RECEIVING' ? '#f59e0b' : '#000000'}
            transparent opacity={s.kind === 'STORAGE' ? 0.12 : 0.3} depthWrite={false} />
        </mesh>
      ))}
    </group>
  );
}
