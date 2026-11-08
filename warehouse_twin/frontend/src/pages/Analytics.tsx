import { useEffect, useState } from 'react';
import { Box, Table, TableBody, TableCell, TableRow, Typography } from '@mui/material';
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { api } from '../api';
import { Card, Stat } from '../components/common';
import { SERIES } from '../theme';

const axis = { stroke: '#475569', tick: { fill: '#94a3b8', fontSize: 11 }, tickLine: false };
const grid = <CartesianGrid stroke="#1f2937" vertical={false} />;
const tip = { contentStyle: { background: '#0f172a', border: '1px solid #334155', fontSize: 12 }, labelStyle: { color: '#e2e8f0' } };
const fmtS = (s: number | null | undefined) => (s == null ? '—' : s < 90 ? `${Math.round(s)} s` : `${(s / 60).toFixed(1)} min`);

export default function Analytics() {
  const [a, setA] = useState<any>(null);
  const [dbs, setDbs] = useState<any>(null);
  useEffect(() => {
    const load = () => { api.get('/api/analytics').then(setA).catch(() => null); api.get('/api/db/stats').then(setDbs).catch(() => null); };
    load();
    const h = setInterval(load, 3000);
    return () => clearInterval(h);
  }, []);
  if (!a) return null;
  const k = a.kpi;
  const fleet = a.fleet.map((f: any) => ({ ...f, name: f.id }));
  const products = Object.entries(a.inventory_by_product).map(([p, n]) => ({ p, n })).sort((x: any, y: any) => y.n - x.n);
  return (
    <Box sx={{ p: 2, display: 'grid', gap: 2 }}>
      <Box sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap' }}>
        <Stat label="Putaways" value={k.putaways} sub={`${a.throughput_per_hour.putaways}/h · avg ${fmtS(a.cycle_avg_s.PUTAWAY)}`} />
        <Stat label="Order picks" value={k.picks} sub={`${a.throughput_per_hour.picks}/h · avg ${fmtS(a.cycle_avg_s.PICK)}`} />
        <Stat label="Rehandles" value={k.relocations} sub="stack dependency moves" />
        <Stat label="Bundles dispatched" value={k.bundles_dispatched} sub={`${k.trucks_dispatched} trucks · dock-to-exit ${fmtS(a.cycle_avg_s.TRUCK)}`} />
        <Stat label="1st-pass dispatch accuracy" value={a.dispatch_accuracy == null ? '—' : `${a.dispatch_accuracy}%`} sub={`${k.gate_validations} gate validations`} />
        <Stat label="Exceptions caught at gate" value={k.exceptions} sub={`${k.exceptions_resolved} resolved before departure`} />
        <Stat label="RFID reads" value={k.rfid_reads} sub="fork readers + gate" />
        <Stat label="Order cycle" value={fmtS(a.cycle_avg_s.ORDER)} sub="release → fully staged" />
      </Box>
      <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0,1fr))', gap: 2 }}>
        <Card title="Cumulative movements this shift">
          <ResponsiveContainer width="100%" height={230}>
            <LineChart data={a.series}>
              {grid}<XAxis dataKey="clock" {...axis} minTickGap={30} /><YAxis {...axis} width={36} /><Tooltip {...tip} /><Legend wrapperStyle={{ fontSize: 12 }} />
              <Line type="monotone" dataKey="putaways" name="Putaways" stroke={SERIES[0]} strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="picks" name="Picks" stroke={SERIES[1]} strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="dispatched" name="Bundles dispatched" stroke={SERIES[2]} strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </Card>
        <Card title="Inventory by location">
          <ResponsiveContainer width="100%" height={230}>
            <AreaChart data={a.series}>
              {grid}<XAxis dataKey="clock" {...axis} minTickGap={30} /><YAxis {...axis} width={36} /><Tooltip {...tip} /><Legend wrapperStyle={{ fontSize: 12 }} />
              <Area type="monotone" dataKey="indoor" name="Indoor WH01" stackId="1" stroke="#111827" strokeWidth={2} fill={SERIES[0]} fillOpacity={0.85} />
              <Area type="monotone" dataKey="yard" name="Yard WH02" stackId="1" stroke="#111827" strokeWidth={2} fill={SERIES[2]} fillOpacity={0.85} />
              <Area type="monotone" dataKey="staging" name="Staging" stackId="1" stroke="#111827" strokeWidth={2} fill={SERIES[3]} fillOpacity={0.85} />
            </AreaChart>
          </ResponsiveContainer>
        </Card>
        <Card title="Forklift utilization (% of shift busy)">
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={fleet}>
              {grid}<XAxis dataKey="name" {...axis} /><YAxis {...axis} width={36} domain={[0, 100]} /><Tooltip {...tip} />
              <Bar dataKey="util" name="Utilization %" radius={[4, 4, 0, 0]} fill={SERIES[0]} barSize={22} />
            </BarChart>
          </ResponsiveContainer>
          <Typography sx={{ fontSize: 11, color: '#64748b' }}>F-01…F-04 putaway · F-05…F-08 picking & dispatch</Typography>
        </Card>
        <Card title="Stock on site by product (bundles)">
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={products} layout="vertical" margin={{ left: 10 }}>
              <CartesianGrid stroke="#1f2937" horizontal={false} /><XAxis type="number" {...axis} /><YAxis type="category" dataKey="p" {...axis} width={70} /><Tooltip {...tip} />
              <Bar dataKey="n" name="Bundles" fill={SERIES[0]} radius={[0, 4, 4, 0]} barSize={14} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
        <Card title="Last 7 days (simulated baseline history)">
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={a.history}>
              {grid}<XAxis dataKey="day" {...axis} /><YAxis {...axis} width={36} /><Tooltip {...tip} /><Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="putaways" name="Putaways" fill={SERIES[0]} radius={[4, 4, 0, 0]} />
              <Bar dataKey="dispatched" name="Dispatched" fill={SERIES[2]} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
        <Card title="Occupancy & system of record">
          <Table size="small"><TableBody>
            <TableRow><TableCell>Indoor WH01 occupancy</TableCell><TableCell align="right"><b>{a.occupancy.WH01}%</b> of {a.capacity.WH01} positions</TableCell></TableRow>
            <TableRow><TableCell>Yard WH02 occupancy</TableCell><TableCell align="right"><b>{a.occupancy.WH02}%</b> of {a.capacity.WH02} positions</TableCell></TableRow>
            <TableRow><TableCell>Staging occupancy</TableCell><TableCell align="right"><b>{a.occupancy.staging}%</b> of {a.capacity.staging}</TableCell></TableRow>
            <TableRow><TableCell>Orders by status</TableCell><TableCell align="right">{Object.entries(a.orders_by_status).map(([s, n]) => `${s} ${n}`).join(' · ')}</TableCell></TableRow>
          </TableBody></Table>
          {dbs && (
            <>
              <Typography sx={{ fontSize: 11, fontWeight: 800, color: '#64748b', mt: 1.5 }}>DATABASE ({dbs.engine.toUpperCase()}) · {dbs.writes} writes</Typography>
              <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', columnGap: 2, fontSize: 11.5 }}>
                {Object.entries(dbs.tables).map(([t, n]) => <Box key={t} sx={{ display: 'flex' }}><Box sx={{ flex: 1, color: '#94a3b8', fontFamily: 'monospace' }}>{t}</Box><b>{n as number}</b></Box>)}
              </Box>
            </>
          )}
        </Card>
      </Box>
    </Box>
  );
}
