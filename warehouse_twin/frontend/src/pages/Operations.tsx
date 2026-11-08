import { Box, Button, LinearProgress, Table, TableBody, TableCell, TableHead, TableRow, Typography } from '@mui/material';
import { useStore } from '../store';
import { Card, StatusChip, clock, mono } from '../components/common';
import { locateBundle } from '../components/TwinPanels';
import type { TaskRow } from '../types';

function TaskTable({ rows, empty }: { rows: TaskRow[]; empty: string }) {
  if (!rows.length) return <Typography sx={{ fontSize: 12, color: '#64748b', py: 1 }}>{empty}</Typography>;
  return (
    <Table size="small">
      <TableHead><TableRow><TableCell>Task</TableCell><TableCell>Bundle</TableCell><TableCell>Forklift</TableCell><TableCell>From → To</TableCell><TableCell>Status</TableCell></TableRow></TableHead>
      <TableBody>
        {rows.map((t) => (
          <TableRow key={t.id} hover sx={{ cursor: 'pointer' }} onClick={() => locateBundle(t.bundle)}>
            <TableCell><b>{t.type}</b><Box sx={{ ...mono, color: '#64748b' }}>{t.id}</Box>{t.note && <Box sx={{ color: '#f59e0b', fontSize: 10.5 }}>{t.note}</Box>}</TableCell>
            <TableCell>{t.barcode}<Box sx={{ color: '#64748b' }}>{t.order}</Box></TableCell>
            <TableCell>{t.forklift}</TableCell>
            <TableCell sx={{ ...mono, fontSize: 10.5, whiteSpace: 'nowrap' }}>{t.from}<br />→ {t.to}</TableCell>
            <TableCell><StatusChip s={t.status} />{t.duration_s != null && <Box sx={{ color: '#64748b' }}>{t.duration_s}s · {t.distance_m} m</Box>}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

export default function Operations() {
  const ops = useStore((s) => s.ops);
  const action = useStore((s) => s.action);
  if (!ops) return null;
  const putaway = ops.active.filter((t) => t.type === 'PUTAWAY');
  const picking = ops.active.filter((t) => t.type === 'PICK' || t.type === 'RELOCATE');
  const dispatch = ops.active.filter((t) => t.type === 'LOAD' || t.type === 'UNLOAD');
  const pickOrders = ops.orders.filter((o) => ['RELEASED', 'PICKING', 'STAGED'].includes(o.status));
  const dock = ops.dock;
  const dockOrder = dock ? ops.orders.find((o) => o.order_number === dock.order) : null;
  return (
    <Box sx={{ p: 2, display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0,1fr))', gap: 2, alignItems: 'start' }}>
      <Box sx={{ display: 'grid', gap: 2 }}>
        <Card title="① Putaway workflow" action={<Button variant="outlined" onClick={() => action('/api/ops/receive', {}, 'Bundle received')}>Receive bundle</Button>}>
          <Typography sx={{ fontSize: 12, color: '#94a3b8', mb: 1 }}>Production → receiving → RFID association → location allocation → putaway forklift (F-01…F-04)</Typography>
          <Typography sx={{ fontSize: 11, fontWeight: 800, color: '#64748b' }}>QUEUED ({ops.queue.filter((q) => q.type === 'PUTAWAY').length})</Typography>
          {ops.queue.filter((q) => q.type === 'PUTAWAY').map((q) => (
            <Box key={q.id} sx={{ fontSize: 12, py: 0.25 }}>{q.barcode} → <span style={mono}>{q.to}</span> · waiting {Math.round(q.waiting_s)}s {q.prefer && `(for ${q.prefer})`}</Box>
          ))}
          <Typography sx={{ fontSize: 11, fontWeight: 800, color: '#64748b', mt: 1 }}>IN PROGRESS</Typography>
          <TaskTable rows={putaway} empty="No putaway task running" />
        </Card>
      </Box>
      <Box sx={{ display: 'grid', gap: 2 }}>
        <Card title="② Picking workflow" action={<Button variant="outlined" onClick={() => action('/api/ops/order', {}, 'Oracle order received')}>Generate order</Button>}>
          <Typography sx={{ fontSize: 12, color: '#94a3b8', mb: 1 }}>Oracle pick release → bundle identification → rehandle planning → picking forklift (F-05…F-08) → staging lane</Typography>
          {pickOrders.length === 0 && <Typography sx={{ fontSize: 12, color: '#64748b' }}>No released orders</Typography>}
          {pickOrders.map((o) => (
            <Box key={o.order_number} sx={{ py: 0.75, borderBottom: '1px solid #1e293b' }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <b style={{ fontSize: 13 }}>{o.order_number}</b><StatusChip s={o.status} />
                <Box sx={{ flex: 1, fontSize: 12, color: '#94a3b8' }}>{o.customer}</Box>
                {o.status === 'RELEASED' && <Button size="small" variant="contained" onClick={() => action('/api/ops/pick', { order: o.order_number }, 'Picking started')}>Start picking</Button>}
              </Box>
              <LinearProgress variant="determinate" value={(100 * o.staged) / Math.max(1, o.bundle_count)} sx={{ mt: 0.5, height: 5, borderRadius: 3 }} />
              <Typography sx={{ fontSize: 11, color: '#64748b' }}>{o.staged}/{o.bundle_count} staged {o.lane && `· ${o.lane}`}</Typography>
            </Box>
          ))}
          <Typography sx={{ fontSize: 11, fontWeight: 800, color: '#64748b', mt: 1 }}>IN PROGRESS</Typography>
          <TaskTable rows={picking} empty="No pick task running" />
          <Typography sx={{ fontSize: 11, fontWeight: 800, color: '#64748b', mt: 1 }}>STAGING LANES</Typography>
          <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
            {Object.entries(ops.lanes).map(([l, o]) => <Box key={l} sx={{ px: 1, py: 0.5, border: '1px solid #334155', borderRadius: 1, fontSize: 12 }}>{l}: <b>{o ?? 'free'}</b></Box>)}
          </Box>
        </Card>
      </Box>
      <Box sx={{ display: 'grid', gap: 2 }}>
        <Card title="③ Dispatch & RFID gate" action={<Button variant="outlined" onClick={() => action('/api/ops/dispatch', {}, 'Truck called')}>Call truck</Button>}>
          <Typography sx={{ fontSize: 12, color: '#94a3b8', mb: 1 }}>Truck arrival → manifest → loading → GATE-01 EPC read → reconciliation → authorize / hold</Typography>
          {dock ? (
            <Box>
              <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}><b>DOCK-1 · {dock.plate}</b><StatusChip s={dock.state} /></Box>
              <Typography sx={{ fontSize: 12 }}>{dock.order} · {dockOrder?.customer} · {dock.onBoard}/{dockOrder?.bundle_count ?? '?'} on board</Typography>
              <LinearProgress variant="determinate" color="secondary" value={(100 * dock.onBoard) / Math.max(1, dockOrder?.bundle_count ?? 1)} sx={{ my: 0.5, height: 5, borderRadius: 3 }} />
              {dock.state === 'LOADED' && <Button variant="contained" onClick={() => action('/api/ops/gate', {}, 'To the gate')}>Release to RFID gate</Button>}
            </Box>
          ) : <Typography sx={{ fontSize: 12, color: '#64748b' }}>Dock free</Typography>}
          <Typography sx={{ fontSize: 11, fontWeight: 800, color: '#64748b', mt: 1 }}>LOADING TASKS</Typography>
          <TaskTable rows={dispatch} empty="No loading in progress" />
          <Typography sx={{ fontSize: 11, fontWeight: 800, color: '#64748b', mt: 1 }}>EXCEPTIONS</Typography>
          {ops.exceptions.length === 0 && <Typography sx={{ fontSize: 12, color: '#64748b' }}>None raised</Typography>}
          {[...ops.exceptions].reverse().map((e) => (
            <Box key={e.id} sx={{ p: 1, my: 0.5, borderRadius: 1, border: `1px solid ${e.resolved ? '#334155' : '#ef4444'}`, fontSize: 12 }}>
              <Box sx={{ display: 'flex', gap: 1 }}><b>{e.id}</b><span>{e.order}</span><span>{clock(e.ts)}</span><Box sx={{ flex: 1 }} /><StatusChip s={e.resolved ? 'DONE' : 'EXCEPTION'} /></Box>
              {e.missing.map((m) => <div key={m.epc}>Missing {m.barcode} — left at {m.location}</div>)}
              {e.unexpected.map((m) => <div key={m.epc}>Unexpected {m.barcode} ({m.so}, {m.customer})</div>)}
              {!e.resolved && <Button size="small" color="error" variant="contained" sx={{ mt: 0.5 }} onClick={() => action('/api/ops/resolve', { exception: e.id }, 'Resolving')}>Resolve</Button>}
            </Box>
          ))}
        </Card>
      </Box>
      <Card title="Recently completed movements" sx={{ gridColumn: '1 / -1' }}>
        <TaskTable rows={ops.recent} empty="Nothing completed yet" />
      </Card>
    </Box>
  );
}
