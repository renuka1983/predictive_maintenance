import { useRef } from 'react';
import * as THREE from 'three';
import { useFrame } from '@react-three/fiber';
import { Html } from '@react-three/drei';
import { useStore } from '../store';

const COLORS: Record<string, string> = { IDLE: '#64748b', READING: '#38bdf8', AUTHORIZED: '#22c55e', EXCEPTION: '#ef4444' };

export function RfidGate() {
  const layout = useStore((s) => s.layout);
  const gate = useStore((s) => s.sim?.gate.state ?? 'IDLE');
  const rfid = useStore((s) => s.toggles.rfid);
  const field = useRef<THREE.Mesh>(null);
  const boom = useRef<THREE.Group>(null);
  useFrame(({ clock }, dt) => {
    if (field.current) {
      const m = field.current.material as THREE.MeshBasicMaterial;
      m.opacity = gate === 'IDLE' ? (rfid ? 0.05 : 0) : 0.18 + 0.12 * Math.sin(clock.elapsedTime * (gate === 'READING' ? 12 : 4));
    }
    if (boom.current) {
      const target = gate === "AUTHORIZED" ? Math.PI / 2.2 : 0;
      boom.current.rotation.z += (target - boom.current.rotation.z) * (1 - Math.exp(-dt * 3));
    }
  });
  if (!layout) return null;
  const { x, z, width, height } = layout.gate;
  const c = COLORS[gate] ?? COLORS.IDLE;
  return (
    <group position={[x, 0, z]}>
      {[-1, 1].map((s) => (
        <group key={s} position={[s * width / 2, 0, 0]}>
          <mesh position={[0, height / 2, 0]} castShadow><boxGeometry args={[0.5, height, 0.7]} /><meshStandardMaterial color="#e2e8f0" metalness={0.4} /></mesh>
          {[1.2, 2.6, 4.0].map((y) => (
            <mesh key={y} position={[-s * 0.3, y, 0]}><boxGeometry args={[0.08, 0.9, 0.5]} /><meshStandardMaterial color={c} emissive={c} emissiveIntensity={0.7} /></mesh>
          ))}
        </group>
      ))}
      <mesh position={[0, height, 0]} castShadow><boxGeometry args={[width + 0.5, 0.6, 0.8]} /><meshStandardMaterial color="#e2e8f0" metalness={0.4} /></mesh>
      <mesh position={[0, height + 0.01, 0.42]}><planeGeometry args={[width - 1, 0.5]} /><meshBasicMaterial color={c} /></mesh>
      <mesh ref={field} position={[0, height / 2, 0]}><boxGeometry args={[width - 0.6, height - 0.4, 3]} /><meshBasicMaterial color={c} transparent opacity={0.1} depthWrite={false} /></mesh>
      {/* exit barrier after the gate */}
      <group position={[-width / 2 - 0.4, 1.1, -6]}>
        <mesh><boxGeometry args={[0.5, 1.2, 0.5]} /><meshStandardMaterial color="#facc15" /></mesh>
        <group ref={boom} position={[0.3, 0.5, 0]}>
          <mesh position={[width / 2, 0, 0]} rotation={[0, 0, 0]}><boxGeometry args={[width, 0.15, 0.15]} /><meshStandardMaterial color={gate === 'EXCEPTION' ? '#ef4444' : '#f8fafc'} /></mesh>
        </group>
      </group>
      <Html zIndexRange={[3, 0]} position={[0, height + 1.4, 0]} center style={{ pointerEvents: 'none' }}>
        <div style={{ background: c, color: 'white', padding: '2px 8px', borderRadius: 4, fontSize: 13, fontWeight: 800,
          fontFamily: 'Roboto, sans-serif', whiteSpace: 'nowrap' }}>RFID GATE-01 · {gate}</div>
      </Html>
    </group>
  );
}
