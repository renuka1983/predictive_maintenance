import { Suspense, lazy, useEffect, useState } from 'react';
import { Alert, Box, Chip, List, ListItemButton, ListItemIcon, ListItemText, Snackbar, Typography } from '@mui/material';
import ViewInArIcon from '@mui/icons-material/ViewInAr';
import SettingsSuggestIcon from '@mui/icons-material/SettingsSuggest';
import Inventory2Icon from '@mui/icons-material/Inventory2';
import ForkliftIcon from '@mui/icons-material/Forklift';
import ReceiptLongIcon from '@mui/icons-material/ReceiptLong';
import InsightsIcon from '@mui/icons-material/Insights';
import { useStore, type PageId } from './store';
import { DemoControlPanel, EventFeed, GateBanner, KpiStrip, ScenarioPanel, SelectionPanel } from './components/TwinPanels';
import Operations from './pages/Operations';
import Inventory from './pages/Inventory';
import Fleet from './pages/Fleet';
import Orders from './pages/Orders';
import Analytics from './pages/Analytics';

const Scene = lazy(() => import('./three/Scene'));

const NAV: { id: PageId; label: string; icon: React.ReactNode; sub: string }[] = [
  { id: 'twin', label: 'Live Digital Twin', icon: <ViewInArIcon />, sub: '3D warehouse & yard' },
  { id: 'operations', label: 'Operations', icon: <SettingsSuggestIcon />, sub: 'Putaway · picking · dispatch' },
  { id: 'inventory', label: 'Inventory', icon: <Inventory2Icon />, sub: 'Bundle search & location' },
  { id: 'fleet', label: 'Fleet', icon: <ForkliftIcon />, sub: '8 forklifts' },
  { id: 'orders', label: 'Orders', icon: <ReceiptLongIcon />, sub: 'Oracle orders & manifests' },
  { id: 'analytics', label: 'Analytics', icon: <InsightsIcon />, sub: 'KPIs' },
];

function Toast() {
  const toast = useStore((s) => s.toast);
  const [open, setOpen] = useState(false);
  useEffect(() => { if (toast) setOpen(true); }, [toast?.nonce]);
  if (!toast) return null;
  return (
    <Snackbar open={open} autoHideDuration={3500} onClose={() => setOpen(false)} anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}>
      <Alert severity={toast.severity} variant="filled" onClose={() => setOpen(false)}>{toast.msg}</Alert>
    </Snackbar>
  );
}

export default function App() {
  const page = useStore((s) => s.page);
  const setPage = useStore((s) => s.setPage);
  const connected = useStore((s) => s.connected);
  const sim = useStore((s) => s.sim);
  const layout = useStore((s) => s.layout);
  return (
    <Box sx={{ display: 'flex', height: '100vh', color: '#e2e8f0' }}>
      <Box sx={{ width: 232, flexShrink: 0, bgcolor: '#0f172a', borderRight: '1px solid #1e293b', display: 'flex', flexDirection: 'column' }}>
        <Box sx={{ p: 2, pb: 1 }}>
          <Typography sx={{ fontWeight: 900, fontSize: 15, lineHeight: 1.2 }}>Bundle Tracking &<br />Dispatch Assurance</Typography>
          <Typography sx={{ fontSize: 11, color: '#64748b', mt: 0.5 }}>Autonomous warehouse digital twin · PoC</Typography>
        </Box>
        <List dense>
          {NAV.map((n) => (
            <ListItemButton key={n.id} selected={page === n.id} onClick={() => setPage(n.id)} sx={{ mx: 1, borderRadius: 1.5, mb: 0.25 }}>
              <ListItemIcon sx={{ minWidth: 34, color: page === n.id ? '#38bdf8' : '#64748b' }}>{n.icon}</ListItemIcon>
              <ListItemText primary={n.label} secondary={n.sub} slotProps={{ primary: { sx: { fontWeight: 700, fontSize: 13 } }, secondary: { sx: { fontSize: 10.5 } } }} />
            </ListItemButton>
          ))}
        </List>
        <Box sx={{ flex: 1 }} />
        <Box sx={{ p: 2, fontSize: 11, color: '#64748b' }}>
          <Chip label={connected ? 'LIVE' : 'RECONNECTING'} color={connected ? 'success' : 'warning'} sx={{ fontWeight: 800, mb: 1 }} />
          <div>Plant {layout?.plant ?? '—'} · {sim?.clock.replace('T', ' ') ?? ''}</div>
          <div>Simulation {sim?.running ? `running ${sim.speed}×` : 'paused'}{sim?.autopilot ? ' · autopilot' : ''}</div>
          <div style={{ marginTop: 6 }}>Simulated data: mock Oracle, RFID & UWB</div>
        </Box>
      </Box>
      <Box sx={{ flex: 1, position: 'relative', overflow: 'hidden' }}>
        <Box sx={{ position: 'absolute', inset: 0, visibility: page === 'twin' ? 'visible' : 'hidden' }}>
          <Suspense fallback={<Box sx={{ p: 4 }}>Loading 3D engine…</Box>}>
            {layout && <Scene active={page === 'twin'} />}
          </Suspense>
          {page === 'twin' && (
            <>
              <DemoControlPanel />
              <ScenarioPanel />
              <GateBanner />
              <SelectionPanel />
              <KpiStrip />
              <EventFeed />
            </>
          )}
        </Box>
        {page !== 'twin' && (
          <Box sx={{ position: 'absolute', inset: 0, overflow: 'auto', bgcolor: '#0b1220' }}>
            {page === 'operations' && <Operations />}
            {page === 'inventory' && <Inventory />}
            {page === 'fleet' && <Fleet />}
            {page === 'orders' && <Orders />}
            {page === 'analytics' && <Analytics />}
          </Box>
        )}
      </Box>
      <Toast />
    </Box>
  );
}
