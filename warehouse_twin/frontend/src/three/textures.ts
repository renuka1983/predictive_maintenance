import * as THREE from 'three';

function canvas(w: number, h: number, draw: (g: CanvasRenderingContext2D) => void) {
  const c = document.createElement('canvas');
  c.width = w; c.height = h;
  draw(c.getContext('2d')!);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 4;
  return t;
}

type Wrap = 'bare' | 'film' | 'paper' | 'kraft';
const WRAP_STYLE: Record<Wrap, { base: string; line: string; strap: string; metal: number; rough: number; print?: string }> = {
  bare: { base: '#d6dbe2', line: '#a7b0bb', strap: '#1e3a8a', metal: 0.3, rough: 0.4 },
  film: { base: '#a9d2f0', line: '#86b9de', strap: '#0f172a', metal: 0.1, rough: 0.3 },
  paper: { base: '#eef0ea', line: '#d7dad2', strap: '#1d4ed8', metal: 0.0, rough: 0.85, print: '#64748b' },
  kraft: { base: '#b98c5a', line: '#a37847', strap: '#111827', metal: 0.0, rough: 0.9, print: '#6b4423' },
};

function sideTexture(w: Wrap) {
  const s = WRAP_STYLE[w];
  return canvas(512, 64, (g) => {
    g.fillStyle = s.base; g.fillRect(0, 0, 512, 64);
    g.strokeStyle = s.line; g.lineWidth = 2;
    for (let y = 6; y < 64; y += 7) { g.beginPath(); g.moveTo(0, y); g.lineTo(512, y); g.stroke(); }
    if (w === 'film') {
      const gr = g.createLinearGradient(0, 0, 0, 64);
      gr.addColorStop(0, 'rgba(255,255,255,0.45)'); gr.addColorStop(0.5, 'rgba(255,255,255,0)'); gr.addColorStop(1, 'rgba(255,255,255,0.25)');
      g.fillStyle = gr; g.fillRect(0, 0, 512, 64);
    }
    if (s.print) {
      g.fillStyle = s.print; g.font = 'bold 18px sans-serif';
      for (let x = 70; x < 512; x += 180) g.fillText('ALU PROFILES', x, 40);
    }
    g.fillStyle = s.strap;
    for (const x of [64, 256, 448]) g.fillRect(x - 6, 0, 12, 64);
  });
}

function endTexture(w: Wrap) {
  const s = WRAP_STYLE[w];
  return canvas(128, 64, (g) => {
    g.fillStyle = '#1f2937'; g.fillRect(0, 0, 128, 64);
    for (let y = 3; y < 64; y += 10) for (let x = 3; x < 128; x += 10) {
      g.fillStyle = w === 'bare' ? '#d1d5db' : '#cbd5e1';
      g.fillRect(x, y, 8, 8);
      g.fillStyle = '#374151'; g.fillRect(x + 2, y + 2, 4, 4);
    }
    if (w !== 'bare') { g.strokeStyle = s.base; g.lineWidth = 6; g.strokeRect(0, 0, 128, 64); }
  });
}

const matCache: Partial<Record<Wrap, THREE.Material[]>> = {};
export function bundleMaterials(w: Wrap): THREE.Material[] {
  if (matCache[w]) return matCache[w]!;
  const s = WRAP_STYLE[w] ?? WRAP_STYLE.bare;
  const side = new THREE.MeshStandardMaterial({ map: sideTexture(w), metalness: s.metal, roughness: s.rough });
  const end = new THREE.MeshStandardMaterial({ map: endTexture(w), metalness: 0.5, roughness: 0.5 });
  // BoxGeometry face order: +x, -x, +y, -y, +z, -z  (long axis = x)
  matCache[w] = [end, end, side, side, side, side];
  return matCache[w]!;
}

export const bundleGeometry = new THREE.BoxGeometry(1, 1, 1);
export const dunnageGeometry = new THREE.BoxGeometry(0.12, 0.08, 1.3);
export const dunnageMaterial = new THREE.MeshStandardMaterial({ color: '#8b5a2b', roughness: 0.95 });

const labelCache = new Map<string, THREE.Texture>();
export function labelTexture(text: string, opts: { color?: string; bg?: string; size?: number; w?: number; h?: number; bold?: boolean } = {}) {
  const key = JSON.stringify([text, opts]);
  if (labelCache.has(key)) return labelCache.get(key)!;
  const { color = '#ffffff', bg = 'rgba(0,0,0,0)', size = 64, w = 1024, h = 128, bold = true } = opts;
  const t = canvas(w, h, (g) => {
    g.fillStyle = bg; g.fillRect(0, 0, w, h);
    g.fillStyle = color;
    let fs = size;
    g.font = `${bold ? 'bold ' : ''}${fs}px "Segoe UI", Roboto, sans-serif`;
    while (fs > 12 && g.measureText(text).width > w * 0.96) {
      fs -= 2;
      g.font = `${bold ? 'bold ' : ''}${fs}px "Segoe UI", Roboto, sans-serif`;
    }
    g.textAlign = 'center'; g.textBaseline = 'middle';
    g.fillText(text, w / 2, h / 2);
  });
  labelCache.set(key, t);
  return t;
}

export function concreteTexture(base = '#a3a8ae') {
  const t = canvas(512, 512, (g) => {
    g.fillStyle = base; g.fillRect(0, 0, 512, 512);
    for (let i = 0; i < 2500; i++) {
      const v = Math.random() * 30 - 15;
      g.fillStyle = `rgba(${v > 0 ? 255 : 0},${v > 0 ? 255 : 0},${v > 0 ? 255 : 0},${Math.abs(v) / 200})`;
      g.fillRect(Math.random() * 512, Math.random() * 512, 2 + Math.random() * 4, 2 + Math.random() * 4);
    }
    g.strokeStyle = 'rgba(0,0,0,0.12)'; g.lineWidth = 2;
    g.strokeRect(0, 0, 512, 512);
  });
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  return t;
}
