import { useEffect, useState } from 'react';
import {
  Box, Button, ButtonGroup, Chip, Divider, IconButton, LinearProgress, MenuItem, Paper, Select, Stack, Switch, Tooltip, Typography,
} from '@mui/material';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import PauseIcon from '@mui/icons-material/Pause';
import RestartAltIcon from '@mui/icons-material/RestartAlt';
import CloseIcon from '@mui/icons-material/Close';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import ErrorIcon from '@mui/icons-material/Error';
import RadioButtonUncheckedIcon from '@mui/icons-material/RadioButtonUnchecked';
import HourglassTopIcon from '@mui/icons-material/HourglassTop';
import { api } from '../api';
import { liveIndex, useStore, type CameraPreset } from '../store';
import { focusFollowCamera } from '../three/CameraRig';
import { KV, SEV_COLOR, SEV_ICON, StatusChip, clock, mono } from './common';

const glass = { bgcolor: 'rgba(15,23,42,0.88)', backdropFilter: 'blur(6px)', border: '1px solid #1e293b' } as const;

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Box sx={{ mt: 1.25 }}>
      <Typography sx={{ fontSize: 10.5, fontWeight: 800, color: '#64748b', letterSpacing: 0.8, mb: 0.5 }}>{title}</Typography>
      {children}
    </Box>
  );
}

export function DemoControlPanel() {
  const sim = useStore((s) => s.sim);
  const ops = useStore((s) => s.ops);
  const toggles = useStore((s) => s.toggles);
  const toggle = useStore((s) => s.toggle);
  const camera = useStore((s) => s.camera);
  const setCamera = useStore((s) => s.setCamera);
  const action = useStore((s) => s.action);
  const setReplay = useStore((s) => s.setReplay);
  const notify = useStore((s) => s.notify);
  const [open, setOpen] = useState(true);
  const [inject, setInject] = useState<'none' | 'wrong' | 'missing'>('none');
  if (!sim) return null;
  const openExc = ops?.exceptions.find((e) => !e.resolved);
  const loaded = sim.trucks.find((t) => t.state === 'LOADED');
  const released = ops?.orders.find((o) => o.status === 'RELEASED');
  const staged = ops?.orders.find((o) => o.status === 'STAGED');
  const B = (p: React.ComponentProps<typeof Button>) => <Button fullWidth variant="outlined" {...p} sx={{ justifyContent: 'flex-start', py: 0.4, fontSize: 12, ...p.sx }} />;

  const replay = async () => {
    try { setReplay(await api.get('/api/replay')); setCamera('overview'); } catch (e) { notify((e as Error).message, 'warning'); }
  };

  return (
    <Paper sx={{ ...glass, position: 'absolute', top: 12, left: 12, width: 292, maxHeight: 'calc(100% - 24px)', overflowY: 'auto', p: 1.5, zIndex: 5 }}>
      <Box sx={{ display: 'flex', alignItems: 'center' }}>
        <Typography sx={{ fontWeight: 800, fontSize: 14, flex: 1 }}>Demo Control Panel</Typography>
        <IconButton size="small" onClick={() => setOpen(!open)}>{open ? <ExpandLessIcon /> : <ExpandMoreIcon />}</IconButton>
      </Box>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 0.5 }}>
        <Tooltip title={sim.running ? 'Pause' : 'Start'}>
          <IconButton color="primary" onClick={() => action(`/api/sim/${sim.running ? 'pause' : 'start'}`)} sx={{ border: '1px solid #334155' }}>
            {sim.running ? <PauseIcon /> : <PlayArrowIcon />}
          </IconButton>
        </Tooltip>
        <Tooltip title="Reset simulation to the seeded demo state">
          <IconButton onClick={() => { useStore.setState({ selection: null, highlightOrder: null, replay: null }); action('/api/sim/reset', {}, 'Simulation reset'); }}
            sx={{ border: '1px solid #334155' }}><RestartAltIcon /></IconButton>
        </Tooltip>
        <Box sx={{ flex: 1, textAlign: 'right' }}>
          <Typography sx={{ ...mono, fontSize: 15, fontWeight: 700, color: '#e2e8f0' }}>{clock(sim.clock)}</Typography>
          <Typography sx={{ fontSize: 10, color: '#64748b' }}>{sim.clock.slice(0, 10)} · plant time</Typography>
        </Box>
      </Box>
      <ButtonGroup size="small" fullWidth sx={{ mt: 1 }}>
        {[1, 2, 3, 5, 10].map((s) => (
          <Button key={s} variant={sim.speed === s ? 'contained' : 'outlined'} onClick={() => action('/api/sim/speed', { speed: s })}>{s}×</Button>
        ))}
      </ButtonGroup>
      {open && (
        <>
          <Section title="VIEW">
            <ButtonGroup size="small" fullWidth>
              {(['overview', 'indoor', 'outdoor', 'dispatch'] as CameraPreset[]).map((c) => (
                <Button key={c} variant={camera === c ? 'contained' : 'outlined'} onClick={() => setCamera(c)} sx={{ fontSize: 11, px: 0.5 }}>{c}</Button>
              ))}
            </ButtonGroup>
            <Button fullWidth size="small" variant={camera === 'follow' ? 'contained' : 'outlined'} sx={{ mt: 0.75 }}
              onClick={focusFollowCamera}>Follow selected forklift</Button>
            <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', mt: 0.5 }}>
              {([['rfid', 'RFID'], ['uwb', 'UWB positioning'], ['routes', 'Routes'], ['labels', 'Labels'], ['roof', 'Roof']] as const).map(([k, l]) => (
                <Box key={k} sx={{ display: 'flex', alignItems: 'center', fontSize: 12 }}>
                  <Switch size="small" checked={toggles[k]} onChange={() => toggle(k)} />{l}
                </Box>
              ))}
            </Box>
          </Section>
          <Section title="SCRIPTED SCENARIOS">
            <Stack spacing={0.6}>
              <B variant="contained" color="success" onClick={() => action('/api/scenario/1').then((r) => r && focusFollowCamera())}>
                ① Automatic putaway (F-01)
              </B>
              <B variant="contained" onClick={() => action('/api/scenario/2').then((r) => {
                if (r) { useStore.setState({ highlightOrder: r.focus.order }); focusFollowCamera(); }
              })}>② Order-based picking (SO-45892)</B>
              <Box sx={{ display: 'flex', gap: 0.5 }}>
                <B variant="contained" color="secondary" sx={{ flex: 1 }} onClick={() => action('/api/scenario/3', { inject: inject === 'none' ? null : inject })
                  .then((r) => { if (r) { useStore.setState({ highlightOrder: r.focus.order }); setCamera('dispatch'); } })}>③ Truck dispatch</B>
                <Select size="small" value={inject} onChange={(e) => setInject(e.target.value as any)} sx={{ fontSize: 11, height: 30, minWidth: 98 }}>
                  <MenuItem value="none">clean</MenuItem>
                  <MenuItem value="wrong">+ wrong</MenuItem>
                  <MenuItem value="missing">+ missing</MenuItem>
                </Select>
              </Box>
            </Stack>
          </Section>
          <Section title="OPERATIONS">
            <Stack spacing={0.6}>
              <Box sx={{ display: 'flex', alignItems: 'center', fontSize: 12 }}>
                <Switch size="small" checked={sim.autoPutaway} onChange={() => action('/api/sim/auto-putaway', { on: !sim.autoPutaway })} />
                Automatic putaway (production flow)
              </Box>
              <B onClick={() => action('/api/ops/receive', {}, 'Bundle received from production')}>Receive bundle from production</B>
              <B onClick={() => action('/api/ops/order', {}).then((r) => r && notify(`Oracle order ${r.order_number} received (${r.customer})`, 'success'))}>
                Generate customer order (Oracle)
              </B>
              <B disabled={!released} onClick={() => action('/api/ops/pick', {}, 'Picking started')}>Start picking {released ? `· ${released.order_number}` : ''}</B>
              <B disabled={!staged || !!ops?.dock} onClick={() => action('/api/ops/dispatch', {}, 'Truck called; forklifts sent to dispatch')}>
                Send forklifts to dispatch {staged ? `· ${staged.order_number}` : ''}
              </B>
              <B disabled={!loaded} onClick={() => action('/api/ops/gate', {}, 'Truck proceeding to the RFID gate')}>Simulate RFID gate validation</B>
              <Box sx={{ display: 'flex', gap: 0.5 }}>
                <B color="warning" onClick={() => action('/api/ops/inject', { kind: 'wrong' }, 'Wrong-bundle error armed')}>Inject wrong</B>
                <B color="warning" onClick={() => action('/api/ops/inject', { kind: 'missing' }, 'Missing-bundle error armed')}>Inject missing</B>
              </Box>
              <B color="error" disabled={!openExc} onClick={() => action('/api/ops/resolve', {}, 'Exception released for correction')}>Resolve dispatch exception</B>
              <B color="secondary" onClick={replay}>Replay previous movement</B>
              <Box sx={{ display: 'flex', alignItems: 'center', fontSize: 12 }}>
                <Switch size="small" color="secondary" checked={sim.autopilot} onChange={() => action('/api/sim/autopilot', { on: !sim.autopilot })} />
                Autopilot (continuous operations)
              </Box>
            </Stack>
          </Section>
        </>
      )}
    </Paper>
  );
}

export function ScenarioPanel() {
  const sc = useStore((s) => s.sim?.scenario);
  if (!sc) return null;
  const done = sc.steps.filter((s) => s.done).length;
  return (
    <Paper sx={{ ...glass, position: 'absolute', top: 12, left: '50%', transform: 'translateX(-50%)', width: 520, p: 1.5, zIndex: 5 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <Chip label={`SCENARIO ${sc.id}`} color="primary" sx={{ fontWeight: 800 }} />
        <Typography sx={{ fontWeight: 800, flex: 1 }}>{sc.title}</Typography>
        {sc.status === 'DONE' && <Chip label="COMPLETE" color="success" sx={{ fontWeight: 800 }} />}
        <IconButton size="small" onClick={() => { api.del('/api/scenario').catch(() => null); }}><CloseIcon fontSize="small" /></IconButton>
      </Box>
      <LinearProgress variant="determinate" value={(100 * done) / sc.steps.length} sx={{ my: 1, height: 5, borderRadius: 3 }} />
      {sc.steps.map((st, i) => {
        const current = !st.done && i === sc.cursor;
        return (
          <Box key={i} sx={{ display: 'flex', gap: 1, alignItems: 'flex-start', py: 0.3, opacity: st.done || current ? 1 : 0.5 }}>
            {st.error ? <ErrorIcon color="error" sx={{ fontSize: 18 }} /> : st.done ? <CheckCircleIcon color="success" sx={{ fontSize: 18 }} />
              : current ? <HourglassTopIcon color="primary" sx={{ fontSize: 18 }} /> : <RadioButtonUncheckedIcon sx={{ fontSize: 18, color: '#475569' }} />}
            <Box sx={{ flex: 1 }}>
              <Typography sx={{ fontSize: 12.5, fontWeight: current ? 800 : 600 }}>{i + 1}. {st.label}</Typography>
              {st.detail && <Typography sx={{ fontSize: 11, color: '#94a3b8' }}>{clock(st.t)} · {st.detail}</Typography>}
            </Box>
          </Box>
        );
      })}
    </Paper>
  );
}

export function EventFeed() {
  const events = useStore((s) => s.events);
  const [filter, setFilter] = useState<'all' | 'key'>('key');
  const KEY = new Set(['BUNDLE_PRODUCED', 'LOCATION_ASSIGNED', 'TASK_ASSIGNED', 'BUNDLE_PLACED', 'BUNDLE_PICKED', 'REHANDLE', 'ORDER_RECEIVED',
    'ORDER_ALLOCATED', 'ORDER_STAGED', 'TRUCK_ARRIVED', 'MANIFEST_CREATED', 'TRUCK_LOADED', 'GATE_READ', 'DISPATCH_VALIDATED',
    'DISPATCH_EXCEPTION', 'OPERATOR_ERROR', 'TRUCK_DEPARTED', 'EXCEPTION_RESOLVING', 'BUNDLE_LOADED', 'RFID_READ', 'SIM_RESET']);
  const list = events.filter((e) => filter === 'all' || KEY.has(e.type)).slice(-14).reverse();
  return (
    <Paper sx={{ ...glass, position: 'absolute', right: 12, bottom: 12, width: 430, p: 1.25, zIndex: 4 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 0.5 }}>
        <Typography sx={{ fontWeight: 800, fontSize: 13, flex: 1 }}>Live event stream</Typography>
        <ButtonGroup size="small">
          <Button variant={filter === 'key' ? 'contained' : 'outlined'} onClick={() => setFilter('key')} sx={{ fontSize: 10.5, py: 0 }}>Key</Button>
          <Button variant={filter === 'all' ? 'contained' : 'outlined'} onClick={() => setFilter('all')} sx={{ fontSize: 10.5, py: 0 }}>All</Button>
        </ButtonGroup>
      </Box>
      <Box sx={{ maxHeight: 250, overflowY: 'auto' }}>
        {list.map((e) => (
          <Box key={e.id} sx={{ display: 'flex', gap: 0.75, py: 0.3, borderBottom: '1px solid #1e293b', fontSize: 11.5 }}>
            <Box sx={{ ...mono, color: '#64748b', fontSize: 10.5, pt: 0.1 }}>{clock(e.ts)}</Box>
            <Box sx={{ color: SEV_COLOR[e.severity], fontWeight: 800, width: 10 }}>{SEV_ICON[e.severity]}</Box>
            <Box sx={{ color: e.severity === 'error' ? '#fecaca' : '#cbd5e1', flex: 1 }}>{e.message}</Box>
          </Box>
        ))}
      </Box>
    </Paper>
  );
}

export function KpiStrip() {
  const ops = useStore((s) => s.ops);
  const sim = useStore((s) => s.sim);
  if (!ops || !sim) return null;
  const k = ops.kpi;
  const acc = k.gate_validations ? `${Math.round((100 * k.first_pass_ok) / k.gate_validations)}%` : '—';
  const items: [string, string | number][] = [
    ['Indoor', ops.inventory.WH01], ['Yard', ops.inventory.WH02], ['Staging', ops.inventory.staging],
    ['Active tasks', ops.active.length], ['Putaways', k.putaways], ['Picks', k.picks], ['Rehandles', k.relocations],
    ['Trucks out', k.trucks_dispatched], ['1st-pass accuracy', acc], ['Exceptions caught', k.exceptions],
  ];
  return (
    <Paper sx={{ ...glass, position: 'absolute', bottom: 12, left: 316, right: 454, p: 0.75, zIndex: 4, display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
      {items.map(([l, v]) => (
        <Box key={l} sx={{ px: 1, py: 0.25, minWidth: 64 }}>
          <Typography sx={{ fontSize: 9.5, color: '#64748b', fontWeight: 700, textTransform: 'uppercase' }}>{l}</Typography>
          <Typography sx={{ fontSize: 16, fontWeight: 800 }}>{v}</Typography>
        </Box>
      ))}
    </Paper>
  );
}

export function GateBanner() {
  const gate = useStore((s) => s.sim?.gate);
  const ops = useStore((s) => s.ops);
  const action = useStore((s) => s.action);
  if (!gate || gate.state === 'IDLE') return null;
  const r = gate.result;
  const exc = ops?.exceptions.find((e) => !e.resolved);
  const color = gate.state === 'AUTHORIZED' ? '#14532d' : gate.state === 'EXCEPTION' ? '#7f1d1d' : '#0c4a6e';
  return (
    <Paper sx={{ position: 'absolute', top: 12, right: 12, width: 360, p: 1.5, zIndex: 6, bgcolor: color, border: '1px solid rgba(255,255,255,.2)' }}>
      <Typography sx={{ fontWeight: 900, fontSize: 15 }}>
        {gate.state === 'READING' ? '📡 RFID gate reading…' : gate.state === 'AUTHORIZED' ? '✔ DISPATCH AUTHORIZED' : '✖ DISPATCH EXCEPTION'}
      </Typography>
      <Typography sx={{ fontSize: 12, mb: 0.5 }}>Truck {gate.truck} · {gate.reads} EPCs read</Typography>
      {r && <Typography sx={{ fontSize: 12 }}>Expected {r.expected} · Read {r.read} · Matched {r.matched}</Typography>}
      {r?.missing.map((m) => <Typography key={m.epc} sx={{ fontSize: 12 }}>Missing: <b>{m.barcode}</b> (at {m.location})</Typography>)}
      {r?.unexpected.map((m) => <Typography key={m.epc} sx={{ fontSize: 12 }}>Unexpected: <b>{m.barcode}</b> belongs to {m.so} / {m.customer}</Typography>)}
      {gate.state === 'EXCEPTION' && exc && (
        <Button variant="contained" sx={{ mt: 1, bgcolor: '#fff', color: '#7f1d1d', '&:hover': { bgcolor: '#fee2e2' } }} onClick={() => action('/api/ops/resolve', {}, 'Correction dispatched')}>
          Resolve: return truck & correct load
        </Button>
      )}
    </Paper>
  );
}

function BundleInfo({ id }: { id: string }) {
  const [d, setD] = useState<any>(null);
  const [h, setH] = useState<any>(null);
  const [stack, setStack] = useState<any>(null);
  const inv = useStore((s) => s.invVersion);
  const select = useStore((s) => s.select);
  useEffect(() => {
    api.get(`/api/bundles/${id}/live`).then((x) => {
      setD(x);
      if (x.location?.stack_id) api.get(`/api/stacks/${x.location.stack_id}`).then(setStack); else setStack(null);
    }).catch(() => setD(null));
    api.get(`/api/bundles/${id}/history`).then(setH).catch(() => null);
  }, [id, inv]);
  if (!d) return <Typography sx={{ fontSize: 12 }}>Loading…</Typography>;
  const L = d.location;
  const lm = d.last_move;
  return (
    <>
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', mb: 0.5 }}>
        <Typography sx={{ fontWeight: 900, fontSize: 15, flex: 1 }}>{d.barcode}</Typography>
        <StatusChip s={d.status} />
      </Box>
      <KV k="RFID EPC" v={d.epc} mono />
      <KV k="Customer" v={d.customer} />
      <KV k="Sales order" v={<>{d.so} <StatusChip s={d.order_status} sx={{ ml: 0.5, height: 16, fontSize: 9 }} /></>} />
      <KV k="Product" v={`${d.product} · ${d.product_name}`} />
      <KV k="Spec / dimension" v={`${d.alloy} · ${d.finish} · L ${d.length_mm} mm · ${d.pieces} pcs · ${d.weight_kg} kg`} />
      <Divider sx={{ my: 0.75 }} />
      <KV k="Location code" v={L.code} mono />
      <KV k="Warehouse" v={L.warehouse_name ?? L.warehouse} />
      {L.kind === 'STACK' && <KV k="Zone / Bay / Stack / Level" v={`${L.zone} (${L.zone_name}) / ${L.bay} / ${L.stack} / L${String(L.level).padStart(2, '0')} of ${d.stack_height}`} />}
      <KV k="Last movement" v={lm ? `${lm.type} · ${clock(lm.ts)} · ${lm.from ? lm.from + ' → ' : ''}${lm.to}` : 'Initial stock (pre-demo)'} />
      <KV k="Handled by" v={lm?.forklift ? <Chip label={lm.forklift} onClick={() => select({ kind: 'forklift', id: lm.forklift })} sx={{ height: 18 }} /> : '—'} />
      {stack && (
        <>
          <Typography sx={{ fontSize: 11, fontWeight: 800, color: '#64748b', mt: 1 }}>STACK {stack.id} · VERTICAL SEQUENCE</Typography>
          {[...stack.levels].reverse().map((lv: any) => (
            <Box key={lv.id} onClick={() => select({ kind: 'bundle', id: lv.id })}
              sx={{ display: 'flex', gap: 1, fontSize: 11.5, px: 0.75, py: 0.25, cursor: 'pointer', borderRadius: 1,
                bgcolor: lv.id === id ? 'rgba(253,224,71,.18)' : 'transparent', '&:hover': { bgcolor: '#1e293b' } }}>
              <Box sx={{ ...mono, color: '#94a3b8' }}>L{String(lv.level).padStart(2, '0')}</Box>
              <Box sx={{ fontWeight: 700 }}>{lv.bc}</Box>
              <Box sx={{ color: '#94a3b8' }}>{lv.so}</Box>
              <Box sx={{ color: '#94a3b8', flex: 1, textAlign: 'right' }}>{lv.p}</Box>
            </Box>
          ))}
        </>
      )}
      {h?.movements?.length > 0 && (
        <>
          <Typography sx={{ fontSize: 11, fontWeight: 800, color: '#64748b', mt: 1 }}>MOVEMENT HISTORY (DATABASE)</Typography>
          {h.movements.slice(0, 6).map((m: any, i: number) => (
            <Box key={i} sx={{ fontSize: 11, color: '#cbd5e1' }}>{clock(m.ts)} · {m.type} · {m.forklift} · <span style={mono}>{m.location}</span></Box>
          ))}
        </>
      )}
    </>
  );
}

function StackInfo({ id }: { id: string }) {
  const [d, setD] = useState<any>(null);
  const inv = useStore((s) => s.invVersion);
  const select = useStore((s) => s.select);
  useEffect(() => { api.get(`/api/stacks/${id}`).then(setD).catch(() => null); }, [id, inv]);
  if (!d) return null;
  return (
    <>
      <Typography sx={{ fontWeight: 900, fontSize: 15 }}>Stack {d.id}</Typography>
      <KV k="Type / zone" v={`${d.kind} · ${d.zone}`} />
      <KV k="Occupancy" v={`${d.levels.length} / ${d.maxLevels} levels${d.incoming ? ` (+${d.incoming} incoming)` : ''}`} />
      <KV k="Access" v={d.locked ? 'Locked by an active forklift job' : 'Free'} />
      {[...d.levels].reverse().map((lv: any) => (
        <Box key={lv.id} onClick={() => select({ kind: 'bundle', id: lv.id })} sx={{ display: 'flex', gap: 1, fontSize: 11.5, py: 0.25, cursor: 'pointer', '&:hover': { color: '#38bdf8' } }}>
          <Box sx={{ ...mono, color: '#94a3b8' }}>L{String(lv.level).padStart(2, '0')}</Box><b>{lv.bc}</b><span>{lv.so}</span><span style={{ color: '#94a3b8' }}>{lv.customer}</span>
        </Box>
      ))}
      {d.levels.length === 0 && <Typography sx={{ fontSize: 12, color: '#94a3b8' }}>Empty floor position</Typography>}
    </>
  );
}

function ForkliftInfo({ id }: { id: string }) {
  const f = useStore((s) => s.sim?.forklifts.find((x) => x.id === id));
  const [hist, setHist] = useState<any[]>([]);
  const setReplay = useStore((s) => s.setReplay);
  const select = useStore((s) => s.select);
  const done = f?.done;
  useEffect(() => { api.get(`/api/forklifts/${id}`).then((x) => setHist(x.history ?? [])).catch(() => null); }, [id, done]);
  if (!f) return null;
  return (
    <>
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
        <Typography sx={{ fontWeight: 900, fontSize: 15, flex: 1 }}>{f.id} · {f.roleLabel}</Typography>
        <StatusChip s={f.state} />
      </Box>
      <KV k="Current task" v={f.task ? `${f.task.type} ${f.task.id}${f.queued ? ` (+${f.queued} queued)` : ''}` : 'None — idle'} />
      <KV k="Position (UWB)" v={`x ${f.x.toFixed(1)} m, z ${f.z.toFixed(1)} m · ${f.warehouse} · ±${Math.round(f.uwbErr * 100)} cm`} />
      <KV k="Load" v={f.load ? <Chip label={f.loadBarcode} onClick={() => select({ kind: 'bundle', id: f.load! })} sx={{ height: 18 }} /> : 'Empty forks'} />
      <KV k="Fork height" v={`${f.fork.toFixed(2)} m`} />
      <KV k="From → to" v={f.task ? `${f.task.from} → ${f.task.to}` : '—'} />
      <KV k="Destination" v={f.dest?.label} />
      <KV k="Order" v={f.task?.order} />
      <KV k="Utilization / battery" v={`${f.util}% · ${f.battery}%`} />
      <KV k="Distance / tasks" v={`${(f.distance / 1000).toFixed(2)} km · ${f.done} tasks`} />
      <Typography sx={{ fontSize: 11, fontWeight: 800, color: '#64748b', mt: 1 }}>MOVEMENT HISTORY</Typography>
      {hist.length === 0 && <Typography sx={{ fontSize: 11.5, color: '#94a3b8' }}>No completed movements yet</Typography>}
      {hist.slice(0, 8).map((h) => (
        <Box key={h.task} sx={{ display: 'flex', gap: 0.75, fontSize: 11, py: 0.25, alignItems: 'center' }}>
          <Box sx={{ ...mono, color: '#94a3b8' }}>{clock(h.end)}</Box>
          <b>{h.type}</b><span>{h.barcode}</span>
          <Box sx={{ flex: 1, color: '#94a3b8', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>→ {h.to}</Box>
          <Button size="small" sx={{ minWidth: 0, py: 0, fontSize: 10.5 }}
            onClick={() => api.get(`/api/replay?task=${h.task}`).then(setReplay).catch(() => null)}>replay</Button>
        </Box>
      ))}
    </>
  );
}

function TruckInfo({ id }: { id: string }) {
  const t = useStore((s) => s.sim?.trucks.find((x) => x.id === id));
  const [o, setO] = useState<any>(null);
  useEffect(() => { if (t?.order) api.get(`/api/orders/${t.order}`).then(setO).catch(() => null); }, [t?.order, t?.state, t?.onBoard]);
  if (!t) return null;
  const mf = o?.manifest_detail;
  return (
    <>
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
        <Typography sx={{ fontWeight: 900, fontSize: 15, flex: 1 }}>Truck {t.plate}</Typography><StatusChip s={t.state} />
      </Box>
      <KV k="Carrier" v={t.carrier} />
      <KV k="Order" v={`${t.order} · ${o?.customer ?? ''}`} />
      <KV k="Manifest" v={t.manifest} mono />
      <KV k="On board" v={`${t.onBoard} bundles`} />
      {mf && (
        <>
          <Typography sx={{ fontSize: 11, fontWeight: 800, color: '#64748b', mt: 1 }}>EXPECTED BUNDLES</Typography>
          {o.pick_list.map((b: any) => (
            <Box key={b.bundle} sx={{ display: 'flex', gap: 1, fontSize: 11.5 }}><b>{b.barcode}</b><StatusChip s={b.status} sx={{ height: 16, fontSize: 9 }} />
              <span style={{ ...mono, color: '#94a3b8' }}>{b.epc.slice(-10)}</span></Box>
          ))}
        </>
      )}
    </>
  );
}

export function SelectionPanel() {
  const sel = useStore((s) => s.selection);
  const select = useStore((s) => s.select);
  const gateActive = useStore((s) => (s.sim?.gate.state ?? 'IDLE') !== 'IDLE');
  if (!sel) return null;
  return (
    <Paper sx={{ ...glass, position: 'absolute', top: gateActive ? 190 : 12, right: 12, width: 380, maxHeight: gateActive ? 'calc(100% - 480px)' : 'calc(100% - 300px)',
      overflowY: 'auto', p: 1.5, zIndex: 5 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 0.5 }}>
        <Typography sx={{ fontSize: 10.5, fontWeight: 800, color: '#38bdf8', letterSpacing: 0.8, flex: 1 }}>{sel.kind.toUpperCase()} DETAILS</Typography>
        <IconButton size="small" onClick={() => select(null)}><CloseIcon fontSize="small" /></IconButton>
      </Box>
      {sel.kind === 'bundle' && <BundleInfo id={sel.id} />}
      {sel.kind === 'forklift' && <ForkliftInfo id={sel.id} />}
      {sel.kind === 'stack' && <StackInfo id={sel.id} />}
      {sel.kind === 'truck' && <TruckInfo id={sel.id} />}
    </Paper>
  );
}

export function locateBundle(id: string) {
  const st = useStore.getState();
  const b = st.bundleIndex[id];
  if (!b || !st.layout) { st.notify('Bundle is not currently in the yard or warehouse', 'warning'); return; }
  if (b.loc.k === 's') {
    const s = st.layout.stacks.find((x) => x.id === (b.loc as any).s)!;
    st.locate({ kind: 'bundle', id }, s.x, s.z);
  } else if (b.loc.k === 'f') {
    const f = liveIndex.forklift((b.loc as any).f)!;
    st.locate({ kind: 'forklift', id: f.id }, f.x, f.z);
  } else if (b.loc.k === 't') {
    const t = liveIndex.truck((b.loc as any).t)!;
    st.locate({ kind: 'truck', id: t.id }, t.x, t.z);
  }
}
