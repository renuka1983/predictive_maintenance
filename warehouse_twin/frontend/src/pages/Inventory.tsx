import { useEffect, useState } from 'react';
import { Box, Button, MenuItem, Table, TableBody, TableCell, TableHead, TableRow, TextField, Typography } from '@mui/material';
import { api } from '../api';
import { useStore } from '../store';
import { Card, Stat, StatusChip, mono } from '../components/common';
import { locateBundle } from '../components/TwinPanels';

export default function Inventory() {
  const [q, setQ] = useState('');
  const [wh, setWh] = useState('');
  const [status, setStatus] = useState('');
  const [rows, setRows] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const inv = useStore((s) => s.invVersion);
  const ops = useStore((s) => s.ops);
  useEffect(() => {
    const h = setTimeout(() => {
      api.get(`/api/inventory/bundles?q=${encodeURIComponent(q)}&warehouse=${wh}&status=${status}&limit=300`)
        .then((r) => { setRows(r.rows); setTotal(r.total); }).catch(() => null);
    }, 250);
    return () => clearTimeout(h);
  }, [q, wh, status, inv]);
  const c = ops?.inventory;
  return (
    <Box sx={{ p: 2, display: 'grid', gap: 2 }}>
      <Box sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap' }}>
        <Stat label="Bundles on site" value={c?.total ?? '—'} sub="tracked by barcode + RFID EPC" />
        <Stat label="Indoor WH01" value={c?.WH01 ?? '—'} />
        <Stat label="Outdoor yard WH02" value={c?.WH02 ?? '—'} />
        <Stat label="Dispatch staging" value={c?.staging ?? '—'} />
        <Stat label="Receiving" value={c?.receiving ?? '—'} />
        <Stat label="On forklifts / trucks" value={`${c?.in_transit ?? 0} / ${c?.on_truck ?? 0}`} />
        <Stat label="Bundle registry (DB rows)" value={total} sub="incl. dispatched" />
      </Box>
      <Card title="Bundle search · system of record">
        <Box sx={{ display: 'flex', gap: 1, mb: 1.5 }}>
          <TextField size="small" autoFocus placeholder="Barcode, EPC, sales order, customer, product or location code…" value={q}
            onChange={(e) => setQ(e.target.value)} sx={{ flex: 1 }} />
          <TextField select size="small" label="Warehouse" value={wh} onChange={(e) => setWh(e.target.value)} sx={{ width: 150 }}>
            <MenuItem value="">All</MenuItem><MenuItem value="WH01">WH01 Indoor</MenuItem><MenuItem value="WH02">WH02 Yard</MenuItem>
          </TextField>
          <TextField select size="small" label="Status" value={status} onChange={(e) => setStatus(e.target.value)} sx={{ width: 150 }}>
            {['', 'RECEIVED', 'STORED', 'IN_TRANSIT', 'STAGED', 'LOADED', 'DISPATCHED'].map((s) => <MenuItem key={s} value={s}>{s || 'All'}</MenuItem>)}
          </TextField>
        </Box>
        <Typography sx={{ fontSize: 11.5, color: '#64748b', mb: 1 }}>{rows.length} shown · click a row to locate the bundle in the 3D twin</Typography>
        <Box sx={{ maxHeight: 'calc(100vh - 330px)', overflow: 'auto' }}>
          <Table size="small" stickyHeader>
            <TableHead><TableRow>
              {['Barcode', 'RFID EPC', 'Customer', 'Sales order', 'Product / dimension', 'Status', 'Location (Plant-WH-Zone-Bay-Stack-Level)', ''].map((h) => <TableCell key={h}>{h}</TableCell>)}
            </TableRow></TableHead>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r.id} hover sx={{ cursor: 'pointer' }} onClick={() => locateBundle(r.id)}>
                  <TableCell><b>{r.barcode}</b></TableCell>
                  <TableCell sx={mono}>{r.epc}</TableCell>
                  <TableCell>{r.customer}</TableCell>
                  <TableCell>{r.sales_order}</TableCell>
                  <TableCell>{r.product_code} · {r.product_name}<Box sx={{ color: '#64748b' }}>{r.alloy} · {r.finish} · {r.length_mm} mm · {r.weight_kg} kg</Box></TableCell>
                  <TableCell><StatusChip s={r.status} /></TableCell>
                  <TableCell sx={mono}>{r.location_code}</TableCell>
                  <TableCell><Button size="small" disabled={r.status === 'DISPATCHED'}>Locate</Button></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Box>
      </Card>
    </Box>
  );
}
