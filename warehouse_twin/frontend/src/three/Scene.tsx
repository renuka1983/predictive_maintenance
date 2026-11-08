import { Canvas } from '@react-three/fiber';
import { OrbitControls, Sky } from '@react-three/drei';
import { useStore } from '../store';
import { Structure } from './Structure';
import { StackBundles } from './Bundles';
import { Forklift } from './Forklift';
import { Trucks } from './Truck';
import { RfidGate } from './Gate';
import { ReplayGhost, RfidPulses, Routes, StackPads, UwbLinks } from './Overlays';
import { CameraRig } from './CameraRig';

function Forklifts() {
  const ids = useStore((s) => (s.sim?.forklifts ?? []).map((f) => f.id).join(','));
  return <>{ids.split(',').filter(Boolean).map((id) => <Forklift key={id} id={id} />)}</>;
}

export default function Scene({ active = true }: { active?: boolean }) {
  const select = useStore((s) => s.select);
  return (
    <Canvas frameloop={active ? "always" : "never"} shadows dpr={[1, 2]} camera={{ position: [-28, 165, 165], fov: 42, near: 0.5, far: 2000 }}
      onPointerMissed={() => select(null)} gl={{ antialias: true, preserveDrawingBuffer: true }}>
      <color attach="background" args={['#9cc3e6']} />
      <fog attach="fog" args={['#9cc3e6', 260, 700]} />
      <Sky sunPosition={[120, 80, 60]} turbidity={6} rayleigh={1.2} />
      <hemisphereLight args={['#e0f2fe', '#475569', 0.9]} />
      <directionalLight position={[80, 140, 70]} intensity={2.0} castShadow shadow-mapSize={[4096, 4096]}
        shadow-camera-left={-140} shadow-camera-right={140} shadow-camera-top={90} shadow-camera-bottom={-90}
        shadow-camera-far={400} shadow-bias={-0.0004} />
      <Structure />
      <StackPads />
      <StackBundles />
      <Forklifts />
      <Trucks />
      <RfidGate />
      <Routes />
      <UwbLinks />
      <RfidPulses />
      <ReplayGhost />
      <OrbitControls makeDefault target={[-24, 0, 8]} maxPolarAngle={Math.PI / 2.1} minDistance={8} maxDistance={420} enableDamping />
      <CameraRig />
    </Canvas>
  );
}
