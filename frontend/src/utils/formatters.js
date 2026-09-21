/** Display formatting helpers shared across pages. */

export const formatNumber = (value, digits = 0) =>
  value === null || value === undefined || Number.isNaN(value)
    ? '--'
    : Number(value).toLocaleString(undefined, {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      });

export const formatCurrency = (value) => {
  if (value === null || value === undefined) return '--';
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `$${(value / 1_000).toFixed(0)}k`;
  return `$${Number(value).toFixed(0)}`;
};

/** Compact currency for axis ticks, where space is tight. */
export const formatAxisCurrency = (value) => {
  if (value === null || value === undefined) return '';
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `$${Math.round(value / 1_000)}k`;
  return `$${Math.round(value)}`;
};

export const formatPercent = (value, digits = 0) =>
  value === null || value === undefined
    ? '--'
    : `${(value * 100).toFixed(digits)}%`;

export const formatHours = (value) => {
  if (value === null || value === undefined) return '--';
  if (value >= 48) return `${(value / 24).toFixed(1)} d`;
  return `${Number(value).toFixed(1)} h`;
};

export const formatDate = (value) =>
  value ? new Date(value).toLocaleDateString(undefined, { dateStyle: 'medium' }) : '--';

export const formatTime = (value) =>
  value
    ? new Date(value).toLocaleTimeString(undefined, {
        hour: '2-digit',
        minute: '2-digit',
      })
    : '--';

export const formatMonth = (value) => {
  if (!value) return '';
  const [year, month] = value.split('-');
  const date = new Date(Number(year), Number(month) - 1, 1);
  return date.toLocaleDateString(undefined, { month: 'short', year: '2-digit' });
};

/** Maps a risk band or severity onto a status token. */
export const statusTone = (band) =>
  ({
    critical: 'critical',
    high: 'serious',
    serious: 'serious',
    medium: 'warning',
    warning: 'warning',
    low: 'good',
    good: 'good',
  })[band] || 'neutral';

/** Maps a machine status onto a status token. */
export const machineTone = (status) =>
  ({
    operational: 'good',
    degraded: 'warning',
    maintenance: 'warning',
    down: 'critical',
    retired: 'neutral',
  })[status] || 'neutral';
