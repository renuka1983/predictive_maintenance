import { useState } from 'react';
import { api } from '../api/client';
import { SimpleBars, StackedBars, TrendLine } from '../components/Charts';
import { ErrorState, Loading } from '../components/States';
import { useApi } from '../hooks/useApi';
import { useTenant } from '../hooks/useTenant';
import {
  formatAxisCurrency,
  formatCurrency,
  formatDate,
  formatHours,
  formatMonth,
  formatNumber,
  formatPercent,
} from '../utils/formatters';

const WINDOWS = [
  { label: 'Last 90 days', value: 90 },
  { label: 'Last 12 months', value: 365 },
  { label: 'Last 3 years', value: 1095 },
];

export default function Maintenance() {
  const { tenantId } = useTenant();
  const [windowDays, setWindowDays] = useState(365);

  const stats = useApi(
    () => api.maintenanceStats(tenantId, windowDays),
    [tenantId, windowDays],
    { enabled: Boolean(tenantId) },
  );
  const recent = useApi(
    () => api.listMaintenance(tenantId, { limit: 25 }),
    [tenantId],
    { enabled: Boolean(tenantId) },
  );

  if (stats.loading) return <Loading label="Loading maintenance KPIs…" />;
  if (stats.error) return <ErrorState error={stats.error} onRetry={stats.reload} />;

  const data = stats.data;
  const trend = data?.monthly_trend || [];

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h1>Maintenance</h1>
          <p>Work-order history and the KPIs derived from it.</p>
        </div>
        <div className="field">
          <label htmlFor="window">Window</label>
          <select
            id="window"
            value={windowDays}
            onChange={(event) => setWindowDays(Number(event.target.value))}
          >
            {WINDOWS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="grid cols-4">
        <div className="stat">
          <span className="stat-label">Work orders</span>
          <span className="stat-value">{formatNumber(data.total_records)}</span>
          <span className="stat-sub">{data.reactive_count} reactive</span>
        </div>
        <div className="stat">
          <span className="stat-label">Planned ratio</span>
          <span className="stat-value">{formatPercent(data.planned_ratio)}</span>
          <span className="stat-sub">higher is better</span>
        </div>
        <div className="stat">
          <span className="stat-label">MTBF</span>
          <span className="stat-value">{formatHours(data.mtbf_hours)}</span>
          <span className="stat-sub">mean time between failures</span>
        </div>
        <div className="stat">
          <span className="stat-label">MTTR</span>
          <span className="stat-value">{formatHours(data.mean_repair_hours)}</span>
          <span className="stat-sub">mean time to repair</span>
        </div>
      </div>

      <div className="grid cols-2">
        <section className="card">
          <div className="card-header">
            <h2>Work orders by month</h2>
          </div>
          <p className="card-note">Planned work versus unplanned breakdowns.</p>
          <StackedBars
            data={trend.map((row) => ({
              month: row.month,
              planned: row.count - row.reactive_count,
              reactive: row.reactive_count,
            }))}
            xKey="month"
            labelFormatter={formatMonth}
            valueFormatter={(value) => formatNumber(value)}
            series={[
              { key: 'planned', label: 'Planned', color: 'var(--series-1)' },
              { key: 'reactive', label: 'Reactive', color: 'var(--series-2)' },
            ]}
          />
        </section>

        <section className="card">
          <div className="card-header">
            <h2>Downtime hours by month</h2>
          </div>
          <p className="card-note">Hours of production lost to maintenance.</p>
          <TrendLine
            data={trend}
            xKey="month"
            valueKey="downtime_hours"
            label="Downtime"
            area
            labelFormatter={formatMonth}
            valueFormatter={(value) => formatHours(value)}
            axisFormatter={(value) => `${Math.round(value)}h`}
          />
        </section>
      </div>

      <section className="card">
        <div className="card-header">
          <h2>Cost by failure mode</h2>
          <span className="muted small">
            {formatCurrency(data.total_cost)} total · {formatCurrency(data.cost_per_machine)} per machine
          </span>
        </div>
        <SimpleBars
          data={(data.top_failure_modes || []).map((row) => ({
            mode: row.failure_mode.replace(/_/g, ' '),
            cost: row.cost,
          }))}
          xKey="mode"
          valueKey="cost"
          horizontal
          height={40 + (data.top_failure_modes?.length || 1) * 30}
          valueFormatter={(value) => formatCurrency(value)}
          axisFormatter={formatAxisCurrency}
        />
      </section>

      <section className="card">
        <div className="card-header">
          <h2>Recent work orders</h2>
        </div>
        {recent.loading ? (
          <Loading />
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Work order</th>
                  <th>Type</th>
                  <th>Failure mode</th>
                  <th>Started</th>
                  <th className="num">Downtime</th>
                  <th className="num">Cost</th>
                </tr>
              </thead>
              <tbody>
                {(recent.data?.items || []).map((record) => (
                  <tr key={record.id}>
                    <td className="primary">{record.work_order_number || '--'}</td>
                    <td>{record.maintenance_type}</td>
                    <td>{record.failure_mode?.replace(/_/g, ' ') || '--'}</td>
                    <td>{formatDate(record.start_time)}</td>
                    <td className="num">{formatHours(record.downtime_hours)}</td>
                    <td className="num">{formatCurrency(record.total_cost)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
