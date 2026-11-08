import type { Layout } from '../types';

export const LEVEL_PITCH = 0.58;
export const DUNNAGE = 0.08;
export const BUNDLE_H = 0.5;
export const BUNDLE_W = 1.2;

export function levelCenterY(level: number, base = 0) {
  return base + DUNNAGE + (level - 1) * LEVEL_PITCH + BUNDLE_H / 2;
}

export function stackIndex(layout: Layout) {
  const m: Record<string, Layout['stacks'][number]> = {};
  for (const s of layout.stacks) m[s.id] = s;
  return m;
}

export const ROLE_COLOR = { PUTAWAY: '#16a34a', PICKING: '#2563eb' } as const;

export function lerpAngle(a: number, b: number, k: number) {
  let d = ((b - a + Math.PI) % (2 * Math.PI)) - Math.PI;
  if (d < -Math.PI) d += 2 * Math.PI;
  return a + d * k;
}
