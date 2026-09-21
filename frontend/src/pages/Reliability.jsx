import { useState } from 'react';
import { api } from '../api/client';
import { ErrorState, Loading, Pill } from '../components/States';
import { useApi } from '../hooks/useApi';
import { useTenant } from '../hooks/useTenant';
import { formatHours, formatNumber, formatPercent } from '../utils/formatters';

/**
 * Level 1 reliability view.
 *
 * The Weibull shape parameter is the actionable output: it says whether
 * time-based replacement will help at all, which is the first real decision
 * a maintenance team can make from CMMS data alone.
 */
export default function Reliability() {
  const { tenantId } = useTenant();
  const [machineId, setMachineId] = useState('');

  const machines = useApi(() => api.listMachines(tenantId, { limit: 200 }), [tenantId], {
    enabled: Boolean(tenantId),
  });
  const fit = useApi(
    () => api.weibull(tenantId, machineId || undefined),
    [tenantId, machineId],
    { enabled: Boolean(tenantId) },
  );

  if (fit.loading) return <Loading label="Fitting reliability curve…" />;
  if (fit.error) return <ErrorState error={fit.error} onRetry={fit.reload} />;

  const data = fit.data;
  const confidenceTone =
    { high: 'good', medium: 'warning', low: 'serious', none: 'neutral' }[data.confidence] ||
    'neutral';

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h1>Reliability</h1>
          <p>Weibull distribution fitted to observed times between failures.</p>
        </div>
        <div className="field">
          <label htmlFor="machine">Scope</label>
          <select
            id="machine"
            value={machineId}
            onChange={(event) => setMachineId(event.target.value)}
          >
            <option value="">All machines</option>
            {(machines.data?.items || []).map((machine) => (
              <option key={machine.id} value={machine.id}>
                {machine.machine_code} — {machine.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="grid cols-4">
        <div className="stat">
          <span className="stat-label">Shape (β)</span>
          <span className="stat-value">{formatNumber(data.shape, 2)}</span>
          <span className="stat-sub">
            {data.shape > 1.15 ? 'wear-out' : data.shape < 0.9 ? 'infant mortality' : 'random'}
          </span>
        </div>
        <div className="stat">
          <span className="stat-label">Characteristic life (η)</span>
          <span className="stat-value">{formatHours(data.scale_hours)}</span>
          <span className="stat-sub">63% have failed by here</span>
        </div>
        <div className="stat">
          <span className="stat-label">MTBF</span>
          <span className="stat-value">{formatHours(data.mtbf_hours)}</span>
          <span className="stat-sub">{data.sample_size} intervals observed</span>
        </div>
        <div className="stat">
          <span className="stat-label">Failure risk, 30 days</span>
          <span className="stat-value">{formatPercent(data.failure_probability_30d, 1)}</span>
          <span className="stat-sub">from the fitted curve</span>
        </div>
      </div>

      <section className="card">
        <div className="card-header">
          <h2>What this means</h2>
          <Pill tone={confidenceTone}>{data.confidence} confidence</Pill>
        </div>
        <p className="small" style={{ color: 'var(--text-secondary)', marginBottom: 0 }}>
          {data.interpretation}
        </p>
      </section>
    </div>
  );
}
