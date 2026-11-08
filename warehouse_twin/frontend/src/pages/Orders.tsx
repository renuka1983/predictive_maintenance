import { useEffect, useState } from 'react';
import { Box, Button, LinearProgress, Tab, Table, TableBody, TableCell, TableHead, TableRow, Tabs, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material';
import { api } from '../api';
import { useStore } from '../store';
import { Card, KV, StatusChip, clock, mono } from '../components/common';
import { locateBundle } from '../components/TwinPanels';

const LOG_FILTERS: Record<string, RegExp> = { All: /./, Putaway: /Putaway|Rehandle/, Picking: /Pick/, Dispatch: /WSH/ };

function OracleLog() {
  const [log, setLog] = useState<any[]>([]);
  const [open, setOpen] = useState<number | null>(null);
  const [filter, setFilter] = useState('All');
  const events = useStore((s) => s.events.length);
  useEffect(() => { api.get('/api/oracle/log?limit=200').then(setLog).catch(() => null); }, [events]);
  return (
    <Card title="Oracle ERP integration log (mock adapter)">
      <Typography sx={{ fontSize: 11.5, color: '#64748b', mb: 1 }}>Messages a production Oracle EBS / Fusion interface would exchange. Click to inspect the payload.</Typography>
      <ToggleButtonGroup size="small" exclusive value={filter} onChange={(_, v) => v && setFilter(v)} sx={{ mb: 1 }}>
        {Object.keys(LOG_FILTERS).map((k) => <ToggleButton key={k} value={k} sx={{ py: 0.2, px: 1.2, fontSize: 11.5, textTransform: 'none' }}>{k}</ToggleButton>)}
      </ToggleButtonGroup>
      <Box sx={{ maxHeight: 520, overflow: 'auto' }}>
        {log.filter((m) => LOG_FILTERS[filter].test(m.interface)).map((m) => (
          <Box key={m.id} onClick={() => setOpen(open === m.id ? null : m.id)} sx={{ py: 0.5, borderBottom: '1px solid #1e293b', cursor: 'pointer', fontSize: 12 }}>
            <Box sx={{ display: 'flex', gap: 1 }}>
              <Box sx={{ ...mono, color: '#64748b' }}>{clock(m.ts)}</Box>
              <Box sx={{ color: m.direction === 'INBOUND' ? '#38bdf8' : '#a78bfa', fontWeight: 800, width: 70 }}>{m.direction === 'INBOUND' ? '⇩ IN' : '⇧ OUT'}</Box>
              <Box sx={{ flex: 1 }}>{m.interface}</Box><b>{m.ref}</b>
            </Box>
            {open === m.id && <Box component="pre" sx={{ ...mono, fontSize: 10.5, bgcolor: '#0b1220', p: 1, borderRadius: 1, overflow: 'auto' }}>{JSON.stringify(m.payload, null, 2)}</Box>}
          </Box>
        ))}
        {log.length === 0 && <Typography sx={{ fontSize: 12, color: '#64748b' }}>No messages yet — generate a customer order.</Typography>}
      </Box>
    </Card>
  );
}

export default function Orders() {
  const ops = useStore((s) => s.ops);
  const action = useStore((s) => s.action);
  const setHighlight = useStore((s) => s.setHighlightOrder);
  const setPage = useStore((s) => s.setPage);
  const [all, setAll] = useState<any[]>([]);
  const [sel, setSel] = useState<string>('SO-45891');
  const [d, setD] = useState<any>(null);
  const [tab, setTab] = useState(0);
  const tick = ops?.kpi ? Object.values(ops.kpi).reduce((a, b) => a + b, 0) : 0;
  useEffect(() => { api.get('/api/orders').then(setAll).catch(() => null); }, [tick]);
  useEffect(() => { if (sel) api.get(`/api/orders/${sel}`).then(setD).catch(() => setD(null)); }, [sel, tick]);
  const list = all.filter((o) => (tab === 0 ? o.status !== 'BOOKED' && o.status !== 'DISPATCHED' : tab === 1 ? o.status === 'BOOKED' : o.status === 'DISPATCHED')).reverse();
  const mf = d?.manifest_detail;
  return (
    <Box sx={{ p: 2, display: 'grid', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1.25fr)', gap: 2, alignItems: 'start' }}>
      <Box sx={{ display: 'grid', gap: 2 }}>
        <Card title="Customer orders (Oracle)" action={<Button variant="contained" onClick={() => action('/api/ops/order', {}).then((r) => r && setSel(r.order_number))}>Generate order</Button>}>
          <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ minHeight: 32, mb: 1 }}>
            <Tab label="Active" sx={{ minHeight: 32, py: 0 }} /><Tab label={`Booked (${all.filter((o) => o.status === 'BOOKED').length})`} sx={{ minHeight: 32, py: 0 }} />
            <Tab label="Dispatched" sx={{ minHeight: 32, py: 0 }} />
          </Tabs>
          <Box sx={{ maxHeight: 380, overflow: 'auto' }}>
            <Table size="small" stickyHeader>
              <TableHead><TableRow><TableCell>Order</TableCell><TableCell>Customer</TableCell><TableCell>Product</TableCell><TableCell>Bundles</TableCell><TableCell>Status</TableCell></TableRow></TableHead>
              <TableBody>
                {list.map((o) => (
                  <TableRow key={o.order_number} hover selected={sel === o.order_number} onClick={() => setSel(o.order_number)} sx={{ cursor: 'pointer' }}>
                    <TableCell><b>{o.order_number}</b><Box sx={{ color: '#64748b' }}>{o.priority}</Box></TableCell>
                    <TableCell>{o.customer}<Box sx={{ color: '#64748b' }}>{o.ship_to}</Box></TableCell>
                    <TableCell>{o.lines[0]?.description}</TableCell>
                    <TableCell>{o.in_stock}/{o.bundle_count}</TableCell>
                    <TableCell><StatusChip s={o.status} /></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Box>
        </Card>
        <OracleLog />
      </Box>
      {d && (
        <Box sx={{ display: 'grid', gap: 2 }}>
          <Card title={<>{d.order_number} · {d.customer} <StatusChip s={d.status} sx={{ ml: 1 }} /></>}
            action={<Button variant="outlined" onClick={() => { setHighlight(d.order_number); setPage('twin'); }}>Highlight in 3D</Button>}>
            <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', columnGap: 2 }}>
              <KV k="Ship to" v={d.ship_to} /><KV k="Carrier" v={d.carrier} />
              <KV k="Booked" v={d.booked_at?.replace('T', ' ')} /><KV k="Released" v={d.released_at?.replace('T', ' ')} />
              <KV k="Staged" v={d.staged_at?.replace('T', ' ')} /><KV k="Dispatched" v={d.dispatched_at?.replace('T', ' ')} />
              <KV k="Staging lane" v={d.lane} /><KV k="Truck" v={d.truck} />
            </Box>
            {d.lines.map((l: any) => (
              <Typography key={l.line} sx={{ fontSize: 12, mt: 1 }}>Line {l.line}: <b>{l.product}</b> {l.description} · {l.alloy} · {l.finish} · {l.qty_bundles} bundles</Typography>
            ))}
            <Box sx={{ display: 'flex', gap: 1, mt: 1 }}>
              {d.status === 'BOOKED' && <Button variant="contained" onClick={() => action('/api/ops/order', { order: d.order_number }, 'Released')}>Release from Oracle</Button>}
              {d.status === 'RELEASED' && <Button variant="contained" onClick={() => action('/api/ops/pick', { order: d.order_number }, 'Picking')}>Start picking</Button>}
              {d.status === 'STAGED' && <Button variant="contained" onClick={() => action('/api/ops/dispatch', { order: d.order_number }, 'Truck called')}>Dispatch (call truck)</Button>}
            </Box>
          </Card>
          <Card title="Pick list">
            <Table size="small">
              <TableHead><TableRow><TableCell>Bundle</TableCell><TableCell>EPC</TableCell><TableCell>Location</TableCell><TableCell>Status</TableCell><TableCell>Last move</TableCell></TableRow></TableHead>
              <TableBody>
                {d.pick_list.map((b: any) => (
                  <TableRow key={b.bundle} hover sx={{ cursor: 'pointer' }} onClick={() => locateBundle(b.bundle)}>
                    <TableCell><b>{b.barcode}</b><Box sx={{ color: '#64748b' }}>{b.length_mm} mm · {b.weight_kg} kg</Box></TableCell>
                    <TableCell sx={mono}>{b.epc}</TableCell>
                    <TableCell sx={mono}>{b.location}</TableCell>
                    <TableCell><StatusChip s={b.status} /></TableCell>
                    <TableCell sx={{ fontSize: 11 }}>{b.last_move ? `${b.last_move.type} · ${b.last_move.forklift ?? ''} · ${clock(b.last_move.ts)}` : '—'}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
          <Card title={`Dispatch manifest ${mf ? mf.id : ''}`}>
            {!mf && <Typography sx={{ fontSize: 12, color: '#64748b' }}>Created when the truck docks.</Typography>}
            {mf && (
              <>
                <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', columnGap: 2 }}>
                  <KV k="Truck" v={`${mf.truck_plate} (${mf.truck_id})`} /><KV k="Oracle delivery" v={mf.delivery_id} />
                  <KV k="Status" v={<StatusChip s={mf.status === 'VALIDATED' ? 'AUTHORIZED' : mf.status} />} /><KV k="Validated" v={mf.validated_at?.replace('T', ' ')} />
                </Box>
                {mf.result && (
                  <Box sx={{ mt: 1, p: 1, borderRadius: 1, border: `1px solid ${mf.result.ok ? '#22c55e' : '#ef4444'}` }}>
                    <Typography sx={{ fontWeight: 800, fontSize: 13 }}>{mf.result.ok ? '✔ Reconciliation passed' : '✖ Reconciliation failed'}</Typography>
                    <Typography sx={{ fontSize: 12 }}>Expected {mf.result.expected} · read {mf.result.read} · matched {mf.result.matched}</Typography>
                    <LinearProgress variant="determinate" color={mf.result.ok ? 'success' : 'error'} value={(100 * mf.result.matched) / Math.max(1, mf.result.expected)} sx={{ my: 0.5 }} />
                    {mf.result.missing.map((m: any) => <div key={m.epc} style={{ fontSize: 12 }}>Missing: {m.barcode} ({m.location})</div>)}
                    {mf.result.unexpected.map((m: any) => <div key={m.epc} style={{ fontSize: 12 }}>Unexpected: {m.barcode} — {m.so} / {m.customer}</div>)}
                  </Box>
                )}
                <Typography sx={{ fontSize: 11, fontWeight: 800, color: '#64748b', mt: 1 }}>RFID GATE READS</Typography>
                <Table size="small">
                  <TableHead><TableRow><TableCell>Time</TableCell><TableCell>EPC</TableCell><TableCell>Bundle</TableCell><TableCell>RSSI</TableCell><TableCell>Ant.</TableCell><TableCell>Reads</TableCell><TableCell>Expected?</TableCell></TableRow></TableHead>
                  <TableBody>
                    {(mf.reads ?? []).slice(-16).map((r: any, i: number) => (
                      <TableRow key={i}>
                        <TableCell sx={mono}>{clock(r.ts)}</TableCell><TableCell sx={mono}>{r.epc}</TableCell><TableCell>{r.barcode}</TableCell>
                        <TableCell>{r.rssi} dBm</TableCell><TableCell>{r.antenna}</TableCell><TableCell>{r.count}</TableCell>
                        <TableCell>{mf.expected_epcs.includes(r.epc) ? <StatusChip s="DONE" /> : <StatusChip s="EXCEPTION" />}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </>
            )}
          </Card>
        </Box>
      )}
    </Box>
  );
}
