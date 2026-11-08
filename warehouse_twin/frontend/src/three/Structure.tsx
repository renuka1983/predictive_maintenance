import { useEffect, useMemo, useRef } from 'react';
import * as THREE from 'three';
import { Line } from '@react-three/drei';
import type { Layout, Rect } from '../types';
import { concreteTexture, labelTexture } from './textures';
import { useStore } from '../store';

const WALL_H = 11;

function Box({ p, s, color, opacity = 1, metal = 0.1, rough = 0.8, cast = false, receive = true }:
  { p: [number, number, number]; s: [number, number, number]; color: string; opacity?: number; metal?: number; rough?: number; cast?: boolean; receive?: boolean }) {
  return (
    <mesh position={p} castShadow={cast} receiveShadow={receive}>
      <boxGeometry args={s} />
      <meshStandardMaterial color={color} transparent={opacity < 1} opacity={opacity} metalness={metal} roughness={rough}
        depthWrite={opacity >= 1} />
    </mesh>
  );
}

function FloorLabel({ text, x, z, w, h = w / 8, color = '#ffffff', rot = 0, y = 0.03, opacity = 0.9 }:
  { text: string; x: number; z: number; w: number; h?: number; color?: string; rot?: number; y?: number; opacity?: number }) {
  const tex = useMemo(() => labelTexture(text, { color }), [text, color]);
  return (
    <mesh position={[x, y, z]} rotation={[-Math.PI / 2, 0, rot]}>
      <planeGeometry args={[w, h]} />
      <meshBasicMaterial map={tex} transparent opacity={opacity} depthWrite={false} />
    </mesh>
  );
}

function RectLine({ r, color, y = 0.025, width = 1.5, dashed = false }: { r: Rect; color: string; y?: number; width?: number; dashed?: boolean }) {
  const [x0, z0, x1, z1] = r;
  return (
    <Line points={[[x0, y, z0], [x1, y, z0], [x1, y, z1], [x0, y, z1], [x0, y, z0]]} color={color} lineWidth={width}
      dashed={dashed} dashSize={1} gapSize={0.6} />
  );
}

function Building({ roof }: { roof: boolean }) {
  const floorTex = useMemo(() => {
    const t = concreteTexture('#9ca3a9');
    t.repeat.set(20, 12);
    return t;
  }, []);
  const cols = [];
  for (let x = -100; x <= 0; x += 10) {
    cols.push(<Box key={`cn${x}`} p={[x, WALL_H / 2, -29.7]} s={[0.5, WALL_H, 0.5]} color="#475569" metal={0.6} />);
    cols.push(<Box key={`cs${x}`} p={[x, WALL_H / 2, 29.7]} s={[0.5, WALL_H, 0.5]} color="#475569" metal={0.6} opacity={0.5} />);
  }
  const trusses = [];
  for (let x = -95; x < 0; x += 10) {
    trusses.push(<Box key={`t${x}`} p={[x, WALL_H - 0.4, 0]} s={[0.35, 0.6, 60]} color="#64748b" metal={0.6} cast={false} />);
  }
  return (
    <group>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[-50, 0.005, 0]} receiveShadow>
        <planeGeometry args={[100, 60]} />
        <meshStandardMaterial map={floorTex} roughness={0.55} metalness={0.05} />
      </mesh>
      {/* north wall (opaque), south wall (cut-away) */}
      <Box p={[-50, WALL_H / 2, -30]} s={[100, WALL_H, 0.3]} color="#cbd5e1" />
      <Box p={[-50, 0.6, 30]} s={[100, 1.2, 0.3]} color="#cbd5e1" />
      <Box p={[-50, WALL_H / 2 + 0.6, 30]} s={[100, WALL_H - 1.2, 0.2]} color="#e2e8f0" opacity={0.12} />
      {/* west wall with production door */}
      <Box p={[-100, WALL_H / 2, -17]} s={[0.3, WALL_H, 26]} color="#cbd5e1" />
      <Box p={[-100, WALL_H / 2, 17]} s={[0.3, WALL_H, 26]} color="#cbd5e1" />
      <Box p={[-100, 8.5, 0]} s={[0.3, 5, 8]} color="#cbd5e1" />
      {/* east wall with yard door */}
      <Box p={[0, WALL_H / 2, -17.5]} s={[0.3, WALL_H, 25]} color="#cbd5e1" opacity={0.45} />
      <Box p={[0, WALL_H / 2, 17.5]} s={[0.3, WALL_H, 25]} color="#cbd5e1" opacity={0.45} />
      <Box p={[0, 8.75, 0]} s={[0.3, 4.5, 10]} color="#cbd5e1" opacity={0.45} />
      <Box p={[0, 6.3, 0]} s={[0.6, 0.5, 10.4]} color="#f59e0b" />
      <Box p={[0, 3.2, -5.1]} s={[0.6, 6.4, 0.3]} color="#f59e0b" />
      <Box p={[0, 3.2, 5.1]} s={[0.6, 6.4, 0.3]} color="#f59e0b" />
      <Box p={[-100, 6.1, 0]} s={[0.6, 0.4, 8.4]} color="#f59e0b" />
      {cols}
      {roof && trusses}
      {roof && <Box p={[-50, WALL_H + 0.1, 0]} s={[100.4, 0.2, 60.4]} color="#94a3b8" opacity={0.35} />}
      {/* production transfer roller table */}
      <Box p={[-103, 0.45, 0]} s={[6, 0.9, 3]} color="#334155" metal={0.5} />
      {[-105, -104, -103, -102, -101].map((x) => (
        <mesh key={x} position={[x, 0.95, 0]} rotation={[Math.PI / 2, 0, 0]}>
          <cylinderGeometry args={[0.1, 0.1, 2.8, 12]} />
          <meshStandardMaterial color="#9ca3af" metalness={0.8} roughness={0.3} />
        </mesh>
      ))}
    </group>
  );
}

function Yard() {
  const posts = useMemo(() => {
    const pts: [number, number][] = [];
    for (let x = 4; x <= 122; x += 3) {
      if (!(x > 107 && x < 119)) { pts.push([x, -35]); pts.push([x, 35]); }
    }
    for (let z = -35; z <= 35; z += 3) { if (Math.abs(z) > 31) continue; pts.push([122, z]); if (Math.abs(z) > 6) pts.push([4, z]); }
    return pts;
  }, []);
  const asphalt = useMemo(() => {
    const t = concreteTexture('#3f454c');
    t.repeat.set(24, 14);
    return t;
  }, []);
  return (
    <group>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[63, 0.004, 0]} receiveShadow>
        <planeGeometry args={[118, 70]} />
        <meshStandardMaterial map={asphalt} roughness={0.95} />
      </mesh>
      {/* access road */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[113, 0.003, 0]} receiveShadow>
        <planeGeometry args={[9, 260]} />
        <meshStandardMaterial color="#2f343a" roughness={0.95} />
      </mesh>
      <Line points={[[113, 0.03, 40], [113, 0.03, 128]]} color="#facc15" lineWidth={2} dashed dashSize={3} gapSize={3} />
      <Line points={[[113, 0.03, -40], [113, 0.03, -128]]} color="#facc15" lineWidth={2} dashed dashSize={3} gapSize={3} />
      {/* fence */}
      {posts.map(([x, z], i) => (
        <mesh key={i} position={[x, 1.1, z]} castShadow>
          <boxGeometry args={[0.12, 2.2, 0.12]} />
          <meshStandardMaterial color="#64748b" metalness={0.6} />
        </mesh>
      ))}
      {[[-35, 4, 107], [-35, 119, 122], [35, 4, 107], [35, 119, 122]].map(([z, a, b], i) => (
        <group key={i}>
          <Box p={[(a + b) / 2, 2.1, z]} s={[b - a, 0.06, 0.06]} color="#94a3b8" metal={0.6} />
          <Box p={[(a + b) / 2, 1.1, z]} s={[b - a, 1.9, 0.02]} color="#94a3b8" opacity={0.18} />
        </group>
      ))}
      {[[122, -31, 31], [4, -35, -6], [4, 6, 35]].map(([x, a, b], i) => (
        <group key={`v${i}`}>
          <Box p={[x, 2.1, (a + b) / 2]} s={[0.06, 0.06, b - a]} color="#94a3b8" metal={0.6} />
          <Box p={[x, 1.1, (a + b) / 2]} s={[0.02, 1.9, b - a]} color="#94a3b8" opacity={0.18} />
        </group>
      ))}
      {/* dock pad */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[113, 0.02, 0]}>
        <planeGeometry args={[4, 15]} />
        <meshStandardMaterial color="#facc15" transparent opacity={0.18} />
      </mesh>
      <FloorLabel text="DOCK-1" x={117.5} z={0} w={10} rot={Math.PI / 2} color="#fde047" />
      <FloorLabel text="TRUCK ENTRY" x={117.8} z={46} w={14} rot={Math.PI / 2} color="#e2e8f0" opacity={0.6} />
      <FloorLabel text="EXIT ▲" x={117.8} z={-52} w={10} rot={Math.PI / 2} color="#e2e8f0" opacity={0.6} />
    </group>
  );
}

function Markings({ layout, labels }: { layout: Layout; labels: boolean }) {
  return (
    <group>
      {layout.zones.map((z) => {
        const [x0, z0, x1, z1] = z.rect;
        return (
          <group key={z.id}>
            <mesh rotation={[-Math.PI / 2, 0, 0]} position={[(x0 + x1) / 2, 0.012, (z0 + z1) / 2]}>
              <planeGeometry args={[x1 - x0, z1 - z0]} />
              <meshBasicMaterial color={z.color} transparent opacity={0.07} depthWrite={false} />
            </mesh>
            <RectLine r={z.rect} color={z.color} width={2} />
          </group>
        );
      })}
      {layout.bays.map((b) => <RectLine key={b.id} r={b.rect} color={b.warehouse_id === 'WH01' ? '#facc15' : '#f8fafc'} width={1.2} />)}
      {/* aisle centre lines */}
      {[-15, 0, 15].map((z) => (
        <group key={z}>
          <Line points={[[-93, 0.02, z], [-8, 0.02, z]]} color="#e2e8f0" lineWidth={1} dashed dashSize={1.5} gapSize={1.5} transparent opacity={0.5} />
          <Line points={[[8, 0.02, z], [104, 0.02, z]]} color="#e2e8f0" lineWidth={1} dashed dashSize={1.5} gapSize={1.5} transparent opacity={0.5} />
        </group>
      ))}
      {labels && layout.zones.map((z) => {
        const [x0, z0, x1, z1] = z.rect;
        const w = Math.min(x1 - x0 - 2, 34);
        const vertical = z1 - z0 > (x1 - x0) * 1.6;
        return <FloorLabel key={`l${z.id}`} text={`${z.warehouse_id}-${z.code} · ${z.name}`} color={z.color}
          x={(x0 + x1) / 2} z={vertical ? (z0 + z1) / 2 : ((z0 + z1) / 2 < 0 ? z0 + 2.2 : z1 - 2.2)}
          w={vertical ? Math.min(z1 - z0 - 4, 34) : w} rot={vertical ? Math.PI / 2 : 0} />;
      })}
      {labels && layout.bays.map((b) => {
        const [x0, z0, x1, z1] = b.rect;
        const north = (z0 + z1) / 2 < 0;
        return <FloorLabel key={`b${b.id}`} text={b.label || b.code} x={(x0 + x1) / 2} z={north ? z0 - 0.9 : z1 + 0.9} w={b.label ? 9 : 5}
          color={b.warehouse_id === 'WH01' ? '#fde68a' : '#e2e8f0'} opacity={0.85} />;
      })}
      {labels && (
        <>
          <FloorLabel text="MAIN AISLE ◀ ▶ YARD DOOR" x={-46} z={0} w={30} color="#94a3b8" opacity={0.55} />
          <FloorLabel text="FROM EXTRUSION / PACKING" x={-96} z={0} w={14} rot={Math.PI / 2} color="#fbbf24" opacity={0.8} />
        </>
      )}
      {layout.parking.map((p) => (
        <mesh key={p.id} rotation={[-Math.PI / 2, 0, 0]} position={[p.x, 0.015, p.z]}>
          <planeGeometry args={[3.4, 2.2]} />
          <meshBasicMaterial color={p.warehouse === 'WH01' ? '#16a34a' : '#2563eb'} transparent opacity={0.25} depthWrite={false} />
        </mesh>
      ))}
    </group>
  );
}

/** Right-hand traffic: a chevron in each lane showing its direction of travel. */
function LaneArrows({ layout }: { layout: Layout }) {
  const ref = useRef<THREE.InstancedMesh>(null);
  const arrows = useMemo(() => {
    const skip = new Set(layout.nolane.map(([a, b]) => [a, b].sort().join('|')));
    const out: { x: number; z: number; rot: number }[] = [];
    for (const [a, b] of layout.graph.edges) {
      if (skip.has([a, b].sort().join('|'))) continue;
      const [ax, az] = layout.graph.nodes[a];
      const [bx, bz] = layout.graph.nodes[b];
      const len = Math.hypot(bx - ax, bz - az);
      if (len < 5) continue;
      const n = Math.max(1, Math.floor(len / 14));
      for (const [sx, sz, ex, ez] of [[ax, az, bx, bz], [bx, bz, ax, az]]) {
        const dx = (ex - sx) / len, dz = (ez - sz) / len;
        const nx = -dz, nz = dx; // right-hand side of travel
        for (let k = 0; k < n; k++) {
          const u = (k + 0.5) / n;
          out.push({ x: sx + (ex - sx) * u + nx * layout.laneOffset, z: sz + (ez - sz) * u + nz * layout.laneOffset,
            rot: Math.atan2(-dz, dx) });
        }
      }
    }
    return out;
  }, [layout]);
  const geom = useMemo(() => {
    const g = new THREE.BufferGeometry();
    // flat chevron pointing along +x, lying on the floor
    const v = [0.9, 0, 0, -0.6, 0, -0.55, -0.25, 0, 0, 0.9, 0, 0, -0.25, 0, 0, -0.6, 0, 0.55];
    g.setAttribute('position', new THREE.Float32BufferAttribute(v, 3));
    g.computeVertexNormals();
    return g;
  }, []);
  useEffect(() => {
    const m = ref.current;
    if (!m) return;
    const o = new THREE.Object3D();
    arrows.forEach((a, i) => {
      o.position.set(a.x, 0.03, a.z);
      o.rotation.set(0, a.rot, 0);
      o.updateMatrix();
      m.setMatrixAt(i, o.matrix);
    });
    m.instanceMatrix.needsUpdate = true;
  }, [arrows]);
  return (
    <instancedMesh ref={ref} args={[geom, undefined, arrows.length]}>
      <meshBasicMaterial color="#f8fafc" transparent opacity={0.55} side={THREE.DoubleSide} depthWrite={false} />
    </instancedMesh>
  );
}

function Anchors({ layout }: { layout: Layout }) {
  return (
    <group>
      {layout.anchors.map((a) => (
        <group key={a.id} position={[a.x, 0, a.z]}>
          {a.warehouse === 'WH02' && (
            <mesh position={[0, a.y / 2, 0]} castShadow>
              <cylinderGeometry args={[0.12, 0.16, a.y, 8]} />
              <meshStandardMaterial color="#64748b" metalness={0.7} roughness={0.4} />
            </mesh>
          )}
          <mesh position={[0, a.y + 0.2, 0]}>
            <boxGeometry args={[0.45, 0.45, 0.45]} />
            <meshStandardMaterial color="#f97316" emissive="#f97316" emissiveIntensity={0.6} />
          </mesh>
        </group>
      ))}
    </group>
  );
}

export function Structure() {
  const layout = useStore((s) => s.layout);
  const toggles = useStore((s) => s.toggles);
  const ground = useMemo(() => new THREE.Color('#4b5a46'), []);
  if (!layout) return null;
  return (
    <group>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[10, -0.02, 0]} receiveShadow>
        <planeGeometry args={[700, 500]} />
        <meshStandardMaterial color={ground} roughness={1} />
      </mesh>
      <Building roof={toggles.roof} />
      <Yard />
      <Markings layout={layout} labels={toggles.labels} />
      {toggles.routes && <LaneArrows layout={layout} />}
      <Anchors layout={layout} />
    </group>
  );
}
