import { useEffect, useRef } from 'react';
import * as THREE from 'three';
import { useFrame, useThree } from '@react-three/fiber';
import { liveIndex, useStore, type CameraPreset } from '../store';

const PRESETS: Record<Exclude<CameraPreset, 'follow'>, { pos: [number, number, number]; target: [number, number, number] }> = {
  overview: { pos: [-28, 165, 165], target: [-24, 0, 8] },
  indoor: { pos: [-70, 42, 52], target: [-62, 0, 2] },
  outdoor: { pos: [46, 55, 70], target: [48, 0, 4] },
  dispatch: { pos: [138, 34, 30], target: [108, 0, -10] },
};

export function CameraRig() {
  const camera = useThree((s) => s.camera);
  const controls = useThree((s) => s.controls) as unknown as { target: THREE.Vector3; update: () => void } | null;
  const preset = useStore((s) => s.camera);
  const nonce = useStore((s) => s.cameraNonce);
  const flyTo = useStore((s) => s.flyTo);
  const anim = useRef<{ p0: THREE.Vector3; p1: THREE.Vector3; t0: THREE.Vector3; t1: THREE.Vector3; start: number } | null>(null);

  const go = (pos: THREE.Vector3, target: THREE.Vector3) => {
    if (!controls) return;
    anim.current = { p0: camera.position.clone(), p1: pos, t0: controls.target.clone(), t1: target, start: performance.now() };
  };

  useEffect(() => {
    if (preset === 'follow' || !controls) return;
    const p = PRESETS[preset];
    go(new THREE.Vector3(...p.pos), new THREE.Vector3(...p.target));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nonce, controls]);

  useEffect(() => {
    if (!flyTo || !controls) return;
    go(new THREE.Vector3(flyTo.x + 14, 22, flyTo.z + 22), new THREE.Vector3(flyTo.x, 0, flyTo.z));
    useStore.setState({ camera: 'overview' });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flyTo?.nonce, controls]);

  useFrame((_, dt) => {
    if (!controls) return;
    const a = anim.current;
    if (a) {
      const u = Math.min(1, (performance.now() - a.start) / 1300);
      const e = u < 0.5 ? 2 * u * u : 1 - Math.pow(-2 * u + 2, 2) / 2;
      camera.position.lerpVectors(a.p0, a.p1, e);
      controls.target.lerpVectors(a.t0, a.t1, e);
      controls.update();
      if (u >= 1) anim.current = null;
      return;
    }
    const st = useStore.getState();
    if (st.camera !== 'follow') return;
    const fid = st.selection?.kind === 'forklift' ? st.selection.id : (st.sim?.scenario?.focus?.forklift ?? null);
    const tid = st.selection?.kind === 'truck' ? st.selection.id : (st.sim?.scenario?.focus?.truck ?? null);
    const obj = fid ? liveIndex.forklift(fid) : tid ? liveIndex.truck(tid) : null;
    if (!obj) return;
    const k = 1 - Math.exp(-dt * 3);
    const dx = (obj.x - controls.target.x) * k, dz = (obj.z - controls.target.z) * k;
    controls.target.x += dx; controls.target.z += dz;
    camera.position.x += dx; camera.position.z += dz;
    controls.update();
  });
  return null;
}

export function focusFollowCamera() {
  const st = useStore.getState();
  st.setCamera('follow');
  const fid = st.selection?.kind === 'forklift' ? st.selection.id : st.sim?.scenario?.focus?.forklift;
  const f = fid ? liveIndex.forklift(fid) : null;
  if (f) useStore.setState((s) => ({ flyTo: { x: f.x, z: f.z, nonce: (s.flyTo?.nonce ?? 0) + 1 }, camera: 'follow' }));
}
