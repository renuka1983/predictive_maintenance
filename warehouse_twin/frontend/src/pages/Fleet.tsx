import { useEffect, useMemo, useState } from 'react';
import { Box, Button, LinearProgress, Paper, Table, TableBody, TableCell, TableHead, TableRow, Typography } from '@mui/material';
import { api } from '../api';
import { useStore } from '../store';
import { Card, KV, StatusChip, clock, mono } from '../components/common';
import { ROLE_COLOR } from '../three/geometry';
import type { HistoryEntry } from '../types';

function MiniMap({ selected, onSelect }: { selected: string; onSelect: (id: string) => void }) {
  const layout = useStore((s) => s.layout);
  const sim = useStore((s) => s.sim);
  if (!layout || !sim) return null;
  const vb = '-104 -40 232 80';
  return (
    <svg viewBox={vb} style={{ width: '100%', background: '#0b1220', borderRadius: 8 }}>
      <rect x={-100} y={-30} width={100} height={60} fill="#1f2937" stroke="#475569" strokeWidth={0.4} />
      <rect x={4} y={-35} width={118} height={70} fill="#111827" stroke="#475569" strokeWidth={0.4} strokeDasharray="1.5 1" />
      {layout.zones.map((z) => <rect key={z.id} x={z.rect[0]} y={z.rect[1]} width={z.rect[2] - z.rect[0]} height={z.rect[3] - z.rect[1]}
        fill={z.color} opacity={0.12} stroke={z.color} strokeWidth={0.3} />)}
      {layout.stacks.map((s) => <rect key={s.id} x={s.x - 3} y={s.z - 0.6} width={6} height={1.2} fill="#64748b" opacity={0.6} />)}
      <text x={-50} y={-32} fill="#94a3b8" fontSize={3} textAnchor="middle">WH01 · Indoor warehouse</text>
      <text x={63} y={-37} fill="#94a3b8" fontSize={3} textAnchor="middle">WH02 · Outdoor yard</text>
      <rect x={108} y={-32.5} width={10} height={1} fill="#38bdf8" />
      {sim.trucks.map((t) => <rect key={t.id} x={t.x - 1.25} y={t.z - 7} width={2.5} height={14} fill="#b91c1c" />)}
      {sim.forklifts.map((f) => (
        <g key={f.id} onClick={() => onSelect(f.id)} style={{ cursor: 'pointer' }}>
          {f.route.length > 1 && <polyline points={f.route.map(([x, z]) => `${x},${z}`).join(' ')} fill="none" stroke={ROLE_COLOR[f.role]} strokeWidth={0.5} strokeDasharray="1 0.7" />}
          <circle cx={f.x} cy={f.z} r={selected === f.id ? 2.4 : 1.7} fill={ROLE_COLOR[f.role]} stroke={selected === f.id ? '#fde047' : '#e2e8f0'} strokeWidth={0.4} />
          <text x={f.x} y={f.z - 2.6} fill="#e2e8f0" fontSize={2.4} textAnchor="middle">{f.id}</text>
        </g>
      ))}
    </svg>
  );
}

export default function Fleet() {
  const forklifts = useStore((s) => s.sim?.forklifts ?? []);
  const setReplay = useStore((s) => s.setReplay);
  const setPage = useStore((s) => s.setPage);
  const locate = useStore((s) => s.locate);
  const [sel, setSel] = useState('F-01');
  const [hist, setHist] = useState<HistoryEntry[]>([]);
  const f = forklifts.find((x) => x.id === sel);
  const done = f?.done;
  useEffect(() => { api.get(`/api/forklifts/${sel}`).then((x) => setHist(x.history ?? [])).catch(() => null); }, [sel, done]);
  const totals = useMemo(() => ({
    util: forklifts.length ? forklifts.reduce((a, f) => a + f.util, 0) / forklifts.length : 0,
    km: forklifts.reduce((a, f) => a + f.distance, 0) / 1000,
  }), [forklifts]);
  return (
    <Box sx={{ p: 2, display: 'grid', gridTemplateColumns: 'minmax(0, 1.4fr) minmax(0, 1fr)', gap: 2, alignItems: 'start' }}>
      <Box sx={{ display: 'grid', gap: 2 }}>
        <Card title={`Live fleet positions (UWB) · avg utilization ${totals.util.toFixed(0)}% · ${totals.km.toFixed(2)} km driven`}>
          <MiniMap selected={sel} onSelect={setSel} />
        </Card>
        <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0,1fr))', gap: 1.5 }}>
          {forklifts.map((x) => (
            <Paper key={x.id} variant="outlined" onClick={() => setSel(x.id)} sx={{ p: 1.25, cursor: 'pointer', borderColor: sel === x.id ? '#fde047' : '#1f2937',
              borderLeft: `4px solid ${ROLE_COLOR[x.role]}` }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                <Typography sx={{ fontWeight: 900, flex: 1 }}>{x.id}</Typography><StatusChip s={x.state} />
              </Box>
              <Typography sx={{ fontSize: 11, color: '#94a3b8' }}>{x.roleLabel}</Typography>
              <Typography sx={{ fontSize: 11.5, mt: 0.5, minHeight: 32 }}>{x.task ? `${x.task.type} · ${x.task.barcode}` : 'Idle'}{x.task?.order ? ` · ${x.task.order}` : ''}</Typography>
              <Typography sx={{ fontSize: 11, color: x.yieldTo ? '#f59e0b' : '#64748b' }}>
                {x.yieldTo ? `Yielding to ${x.yieldTo}` : 'Right of way'} · waited {x.waitS}s
              </Typography>
              <Typography sx={{ fontSize: 11, color: '#94a3b8' }}>{x.warehouse} · ({x.x.toFixed(0)}, {x.z.toFixed(0)})</Typography>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mt: 0.5 }}>
                <Typography sx={{ fontSize: 10.5, color: '#94a3b8', width: 30 }}>Util</Typography>
                <LinearProgress variant="determinate" value={x.util} sx={{ flex: 1, height: 5, borderRadius: 3 }} />
                <Typography sx={{ fontSize: 10.5, width: 34, textAlign: 'right' }}>{x.util.toFixed(0)}%</Typography>
              </Box>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                <Typography sx={{ fontSize: 10.5, color: '#94a3b8', width: 30 }}>Batt</Typography>
                <LinearProgress variant="determinate" color={x.battery < 30 ? 'error' : 'success'} value={x.battery} sx={{ flex: 1, height: 5, borderRadius: 3 }} />
                <Typography sx={{ fontSize: 10.5, width: 34, textAlign: 'right' }}>{x.battery.toFixed(0)}%</Typography>
              </Box>
            </Paper>
          ))}
        </Box>
      </Box>
      {f && (
        <Card title={`${f.id} · ${f.roleLabel}`} action={<Button variant="contained" onClick={() => locate({ kind: 'forklift', id: f.id }, f.x, f.z)}>Show in 3D</Button>}>
          <KV k="State" v={<StatusChip s={f.state} />} />
          <KV k="Current task" v={f.task ? `${f.task.type} ${f.task.id} · ${f.task.barcode}` : 'None'} />
          <KV k="From → to" v={f.task ? `${f.task.from} → ${f.task.to}` : '—'} />
          <KV k="Destination" v={f.dest?.label} />
          <KV k="Load" v={f.loadBarcode ?? 'Empty'} />
          <KV k="Position" v={`x ${f.x.toFixed(2)}, z ${f.z.toFixed(2)} · heading ${((f.h * 180) / Math.PI).toFixed(0)}° · forks ${f.fork.toFixed(2)} m`} />
          <KV k="UWB fix" v={`±${Math.round(f.uwbErr * 100)} cm`} />
          <KV k="Traffic" v={`${f.yieldTo ? `yielding to ${f.yieldTo}` : 'right of way'} · ${f.waitS}s waited this shift`} />
          <KV k="Tasks / distance" v={`${f.done} · ${(f.distance / 1000).toFixed(2)} km`} />
          <Typography sx={{ fontSize: 11, fontWeight: 800, color: '#64748b', mt: 1.5, mb: 0.5 }}>MOVEMENT HISTORY</Typography>
          <Table size="small">
            <TableHead><TableRow><TableCell>End</TableCell><TableCell>Type</TableCell><TableCell>Bundle</TableCell><TableCell>Route</TableCell><TableCell /></TableRow></TableHead>
            <TableBody>
              {hist.map((h) => (
                <TableRow key={h.task}>
                  <TableCell sx={mono}>{clock(h.end)}</TableCell>
                  <TableCell><b>{h.type}</b><Box sx={{ color: '#64748b' }}>{h.duration_s}s · {h.distance_m} m</Box></TableCell>
                  <TableCell>{h.barcode}<Box sx={{ color: '#64748b' }}>{h.order}</Box></TableCell>
                  <TableCell sx={{ ...mono, fontSize: 10.5 }}>{h.from}<br />→ {h.to}</TableCell>
                  <TableCell><Button size="small" onClick={() => api.get(`/api/replay?task=${h.task}`).then((r) => { setReplay(r); setPage('twin'); })}>Replay</Button></TableCell>
                </TableRow>
              ))}
              {hist.length === 0 && <TableRow><TableCell colSpan={5} sx={{ color: '#64748b' }}>No movements yet</TableCell></TableRow>}
            </TableBody>
          </Table>
        </Card>
      )}
    </Box>
  );
}
