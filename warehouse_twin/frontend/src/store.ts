import { create } from 'zustand';
import { api } from './api';
import type { BundleBrief, Layout, Ops, Replay, Selection, SimEvent, SimState } from './types';

export type PageId = 'twin' | 'operations' | 'inventory' | 'fleet' | 'orders' | 'analytics';
export type CameraPreset = 'overview' | 'indoor' | 'outdoor' | 'dispatch' | 'follow';

export interface Pulse { id: number; x: number; z: number; born: number; color: string; big?: boolean }

interface Store {
  connected: boolean;
  layout: Layout | null;
  sim: SimState | null;
  bundles: BundleBrief[];
  bundleIndex: Record<string, BundleBrief>;
  invVersion: number;
  events: SimEvent[];
  ops: Ops | null;
  page: PageId;
  selection: Selection;
  camera: CameraPreset;
  cameraNonce: number;
  flyTo: { x: number; z: number; nonce: number } | null;
  toggles: { rfid: boolean; uwb: boolean; routes: boolean; roof: boolean; labels: boolean };
  highlightOrder: string | null;
  replay: Replay | null;
  pulses: Pulse[];
  toast: { msg: string; severity: 'success' | 'error' | 'info' | 'warning'; nonce: number } | null;
  setPage: (p: PageId) => void;
  select: (s: Selection) => void;
  setCamera: (c: CameraPreset) => void;
  toggle: (k: keyof Store['toggles']) => void;
  setHighlightOrder: (o: string | null) => void;
  setReplay: (r: Replay | null) => void;
  notify: (msg: string, severity?: 'success' | 'error' | 'info' | 'warning') => void;
  locate: (sel: Selection, x: number, z: number) => void;
  action: (url: string, body?: unknown, okMsg?: string) => Promise<any>;
}

let pulseId = 0;

export const useStore = create<Store>((set, get) => ({
  connected: false,
  layout: null,
  sim: null,
  bundles: [],
  bundleIndex: {},
  invVersion: 0,
  events: [],
  ops: null,
  page: (location.hash.replace('#', '') as PageId) || 'twin',
  selection: null,
  camera: 'overview',
  cameraNonce: 0,
  flyTo: null,
  toggles: { rfid: true, uwb: false, routes: true, roof: false, labels: true },
  highlightOrder: null,
  replay: null,
  pulses: [],
  toast: null,
  setPage: (page) => { location.hash = page; set({ page }); },
  select: (selection) => set({ selection }),
  setCamera: (camera) => set((s) => ({ camera, cameraNonce: s.cameraNonce + 1 })),
  toggle: (k) => set((s) => ({ toggles: { ...s.toggles, [k]: !s.toggles[k] } })),
  setHighlightOrder: (highlightOrder) => set({ highlightOrder }),
  setReplay: (replay) => set({ replay: replay ? { ...replay, startedAt: performance.now() } : null }),
  notify: (msg, severity = 'info') => set((s) => ({ toast: { msg, severity, nonce: (s.toast?.nonce ?? 0) + 1 } })),
  locate: (selection, x, z) => set((s) => ({ selection, page: 'twin', flyTo: { x, z, nonce: (s.flyTo?.nonce ?? 0) + 1 } })),
  action: async (url, body = {}, okMsg) => {
    try {
      const r = await api.post(url, body);
      if (okMsg) get().notify(okMsg, 'success');
      return r;
    } catch (e) {
      get().notify((e as Error).message, 'error');
      return null;
    }
  },
}));

const RFID_EVENT_COLORS: Record<string, string> = { RFID_READ: '#22d3ee', RFID_ASSOCIATED: '#facc15', GATE_READ: '#38bdf8' };

export function connect() {
  api.get<Layout>('/api/layout').then((layout) => useStore.setState({ layout })).catch(() => setTimeout(connect, 2000));
  const open = () => {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${proto}://${location.host}/ws`);
    ws.onopen = () => useStore.setState({ connected: true });
    ws.onclose = () => { useStore.setState({ connected: false }); setTimeout(open, 1500); };
    ws.onmessage = (ev) => {
      const m = JSON.parse(ev.data);
      if (m.type === 'state') {
        const { type: _t, ...sim } = m;
        useStore.setState({ sim });
      } else if (m.type === 'inventory') {
        const idx: Record<string, BundleBrief> = {};
        for (const b of m.bundles as BundleBrief[]) idx[b.id] = b;
        useStore.setState({ bundles: m.bundles, bundleIndex: idx, invVersion: m.version });
      } else if (m.type === 'events') {
        const now = performance.now();
        const newPulses: Pulse[] = [];
        if (!m.replace) {
          for (const e of m.events as SimEvent[]) {
            if (e.refs?.rfid && e.refs.x !== undefined) {
              newPulses.push({ id: ++pulseId, x: e.refs.x, z: e.refs.z, born: now, color: RFID_EVENT_COLORS[e.type] ?? '#22d3ee', big: e.type === 'GATE_READ' });
            }
          }
        }
        useStore.setState((s) => ({
          events: m.replace ? m.events : [...s.events, ...m.events].slice(-300),
          pulses: [...s.pulses.filter((p) => now - p.born < 2500), ...newPulses],
        }));
      } else if (m.type === 'ops') {
        const { type: _t, ...ops } = m;
        useStore.setState({ ops });
      }
    };
  };
  open();
}

/** Mutable per-frame forklift poses for smooth interpolation, read inside useFrame. */
export const liveIndex = {
  forklift(id: string) { return useStore.getState().sim?.forklifts.find((f) => f.id === id); },
  truck(id: string) { return useStore.getState().sim?.trucks.find((t) => t.id === id); },
};

// Handy for scripted demos and automated UI checks (e.g. Playwright): window.__twin.getState()
(window as unknown as { __twin: typeof useStore }).__twin = useStore;

window.addEventListener('hashchange', () => {
  const p = location.hash.replace('#', '') as PageId;
  if (p && p !== useStore.getState().page) useStore.setState({ page: p });
});
