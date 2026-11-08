import { createTheme } from '@mui/material/styles';

export const theme = createTheme({
  palette: {
    mode: 'dark',
    primary: { main: '#38bdf8' },
    secondary: { main: '#a78bfa' },
    background: { default: '#0b1220', paper: '#111827' },
    success: { main: '#22c55e' },
    warning: { main: '#f59e0b' },
    error: { main: '#ef4444' },
  },
  shape: { borderRadius: 8 },
  typography: { fontFamily: 'Inter, "Segoe UI", Roboto, sans-serif', fontSize: 13 },
  components: {
    MuiPaper: { styleOverrides: { root: { backgroundImage: 'none' } } },
    MuiButton: { defaultProps: { size: 'small', disableElevation: true }, styleOverrides: { root: { textTransform: 'none', fontWeight: 600 } } },
    MuiChip: { defaultProps: { size: 'small' } },
    MuiTableCell: { styleOverrides: { root: { padding: '5px 8px', fontSize: 12, borderColor: '#1f2937' }, head: { fontWeight: 700, color: '#94a3b8' } } },
  },
});

/** Categorical series slots (validated against the #111827 dark surface). */
export const SERIES = ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#9085e9'];

export const STATUS_COLOR: Record<string, 'default' | 'info' | 'success' | 'warning' | 'error' | 'primary' | 'secondary'> = {
  BOOKED: 'default', RELEASED: 'info', PICKING: 'primary', STAGED: 'secondary', LOADING: 'warning', LOADED: 'warning',
  AT_GATE: 'info', DISPATCHED: 'success', EXCEPTION: 'error',
  STORED: 'default', RECEIVED: 'warning', IN_TRANSIT: 'primary', LOADED_B: 'warning', PRODUCED: 'warning',
  IDLE: 'default', TO_PICKUP: 'primary', PICKING_UP: 'info', TO_DROP: 'secondary', PLACING: 'info', RETURNING: 'default',
  DONE: 'success', IN_PROGRESS: 'primary', ASSIGNED: 'info', CANCELLED: 'error',
  ARRIVING: 'info', AT_DOCK: 'warning', TO_GATE: 'info', READING: 'info', AUTHORIZED: 'success', RETURNING_T: 'warning',
};
