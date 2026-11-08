import { Box, Chip, Paper, Typography, type SxProps } from '@mui/material';
import type { ReactNode } from 'react';
import { STATUS_COLOR } from '../theme';

export function StatusChip({ s, sx }: { s: string | null | undefined; sx?: SxProps }) {
  if (!s) return null;
  return <Chip label={s.replace(/_/g, ' ')} color={STATUS_COLOR[s] ?? 'default'} variant={STATUS_COLOR[s] ? 'filled' : 'outlined'}
    sx={{ fontWeight: 700, fontSize: 10.5, height: 20, ...sx }} />;
}

export function Card({ title, action, children, sx }: { title?: ReactNode; action?: ReactNode; children: ReactNode; sx?: SxProps }) {
  return (
    <Paper variant="outlined" sx={{ p: 1.5, borderColor: '#1f2937', ...sx }}>
      {(title || action) && (
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 1, gap: 1 }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 700, flex: 1, color: '#e2e8f0' }}>{title}</Typography>
          {action}
        </Box>
      )}
      {children}
    </Paper>
  );
}

export function Stat({ label, value, sub, color }: { label: string; value: ReactNode; sub?: ReactNode; color?: string }) {
  return (
    <Paper variant="outlined" sx={{ p: 1.25, borderColor: '#1f2937', minWidth: 120 }}>
      <Typography sx={{ fontSize: 11, color: '#94a3b8', fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.4 }}>{label}</Typography>
      <Typography sx={{ fontSize: 22, fontWeight: 800, color: color ?? '#f1f5f9', lineHeight: 1.2 }}>{value}</Typography>
      {sub && <Typography sx={{ fontSize: 11, color: '#94a3b8' }}>{sub}</Typography>}
    </Paper>
  );
}

export function KV({ k, v, mono }: { k: string; v: ReactNode; mono?: boolean }) {
  return (
    <Box sx={{ display: 'flex', gap: 1, py: 0.25, fontSize: 12 }}>
      <Box sx={{ color: '#94a3b8', minWidth: 112 }}>{k}</Box>
      <Box sx={{ color: '#f1f5f9', fontFamily: mono ? 'ui-monospace, Menlo, monospace' : undefined, wordBreak: 'break-all', fontWeight: 500 }}>{v ?? '—'}</Box>
    </Box>
  );
}

export const clock = (iso?: string | null) => (iso ? iso.slice(11, 19) : '—');
export const mono = { fontFamily: 'ui-monospace, Menlo, monospace', fontSize: 11.5 } as const;

export const SEV_COLOR: Record<string, string> = { info: '#94a3b8', success: '#22c55e', warning: '#f59e0b', error: '#ef4444' };
export const SEV_ICON: Record<string, string> = { info: '•', success: '✔', warning: '▲', error: '✖' };
