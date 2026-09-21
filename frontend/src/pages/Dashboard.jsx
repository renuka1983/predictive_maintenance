import { api } from '../api/client';
import { StackedBars, SimpleBars, TrendLine } from '../components/Charts';
import { ErrorState, Loading, Meter, Pill } from '../components/States';
import { useApi } from '../hooks/useApi';
import { useTenant } from '../hooks/useTenant';
import { LEVEL_NAMES } from '../utils/constants';
import {
  formatAxisCurrency,
  formatCurrency,
  formatHours,
  formatMonth,
  formatNumber,
  formatPercent,
  statusTone,
} from '../utils/formatters';

function Stat({ label, value, sub }) {
  return (
    <div className="stat">
      <span className="stat-label">{label}</span>
      <span className="stat-value">{value}</span>
      {sub && <span className="stat-sub">{sub}</span>}
    </div>
  );
}

export default function Dashboard() {
  const { tenantId } = useTenant();
  const { data, error, loading, reload } = useApi(
    () => api.dashboard(tenantId),
    [tenantId],
    { enabled: Boolean(tenantId) },
  );

  if (loading) return <Loading label="Loading dashboard…" />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data) return null;

  const maintenance = data.maintenance_summary;
  const trend = maintenance?.monthly_trend || [];

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h1>{data.tenant_name}</h1>
          <p>
            Maturity Level {data.maturity_level} · {LEVEL_NAMES[data.maturity_level]} ·{' '}
            {data.enabled_features.length} features unlocked
          </p>
        </div>
      </div>

      <div className="grid cols-4">
        <Stat
          label="Maturity score"
          value={`${formatNumber(data.maturity_score)}`}
          sub="out of 100"
        />
        <Stat
          label="Machines"
          value={formatNumber(data.machine_count)}
          sub={`${data.machines_down} currently down`}
        />
        {maintenance ? (
          <>
            <Stat
              label="Maintenance spend"
              value={formatCurrency(maintenance.total_cost)}
              sub="trailing 12 months"
            />
            <Stat
              label="Planned ratio"
              value={formatPercent(maintenance.planned_ratio)}
              sub={`${maintenance.reactive_count} reactive events`}
            />
          </>
        ) : (
          <>
            <Stat label="Maintenance spend" value="--" sub="Import CMMS data" />
            <Stat label="Planned ratio" value="--" sub="Import CMMS data" />
          </>
        )}
      </div>

      {/* ---------------- Level 1 ---------------- */}
      {maintenance && (
        <div className="grid cols-2">
          <section className="card">
            <div className="card-header">
              <h2>Work orders by month</h2>
              <span className="muted small">
                MTBF {formatHours(maintenance.mtbf_hours)}
              </span>
            </div>
            <p className="card-note">
              Planned work displacing reactive work is the core Level 1 signal.
            </p>
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
              <h2>Maintenance cost by month</h2>
            </div>
            <p className="card-note">
              Total labour and parts across all machines, in dollars.
            </p>
            <TrendLine
              data={trend}
              xKey="month"
              valueKey="cost"
              label="Cost"
              area
              labelFormatter={formatMonth}
              valueFormatter={(value) => formatCurrency(value)}
              axisFormatter={formatAxisCurrency}
            />
          </section>
        </div>
      )}

      {maintenance?.top_failure_modes?.length > 0 && (
        <section className="card">
          <div className="card-header">
            <h2>Cost by failure mode</h2>
          </div>
          <p className="card-note">
            Where the money goes — the shortlist for a reliability programme.
          </p>
          <SimpleBars
            data={maintenance.top_failure_modes.map((row) => ({
              mode: row.failure_mode.replace(/_/g, ' '),
              cost: row.cost,
            }))}
            xKey="mode"
            valueKey="cost"
            horizontal
            height={40 + maintenance.top_failure_modes.length * 30}
            valueFormatter={(value) => formatCurrency(value)}
            axisFormatter={formatAxisCurrency}
          />
        </section>
      )}

      {/* ---------------- Level 2 ---------------- */}
      {(data.top_risks || data.line_summary) && (
        <div className="grid cols-2">
          {data.top_risks && (
            <section className="card">
              <div className="card-header">
                <h2>Highest failure risk</h2>
                <span className="muted small">next 30 days</span>
              </div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Machine</th>
                      <th>Band</th>
                      <th className="num">Risk</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.top_risks.map((risk) => (
                      <tr key={risk.machine_id}>
                        <td className="primary">{risk.machine_code}</td>
                        <td>
                          <Pill tone={statusTone(risk.risk_band)}>{risk.risk_band}</Pill>
                        </td>
                        <td className="num">
                          <Meter
                            value={risk.risk_score}
                            tone={statusTone(risk.risk_band)}
                            label={formatPercent(risk.risk_score)}
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {data.line_summary?.length > 0 && (
            <section className="card">
              <div className="card-header">
                <h2>Line effectiveness</h2>
                <span className="muted small">OEE, last 30 days</span>
              </div>
              <SimpleBars
                data={data.line_summary.map((line) => ({
                  line: line.production_line,
                  oee: line.line_oee,
                }))}
                xKey="line"
                valueKey="oee"
                valueFormatter={(value) => formatPercent(value, 1)}
                axisFormatter={(value) => formatPercent(value)}
                height={200}
              />
            </section>
          )}
        </div>
      )}

      {/* ---------------- Level 3 ---------------- */}
      {(data.active_anomalies !== null || data.rul_watchlist) && (
        <div className="grid cols-2">
          <section className="card">
            <div className="card-header">
              <h2>Anomalies detected</h2>
              <span className="muted small">last 24 hours</span>
            </div>
            <div className="stat" style={{ border: 'none', padding: 0 }}>
              <span className="stat-value">{formatNumber(data.active_anomalies)}</span>
              <span className="stat-sub">
                Outlier sensor readings flagged across instrumented machines.
              </span>
            </div>
          </section>

          {data.rul_watchlist?.length > 0 && (
            <section className="card">
              <div className="card-header">
                <h2>Remaining useful life</h2>
                <span className="muted small">soonest first</span>
              </div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Machine</th>
                      <th>Driver</th>
                      <th className="num">RUL</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.rul_watchlist.map((item) => (
                      <tr key={item.machine_id}>
                        <td className="primary">{item.machine_code}</td>
                        <td>{item.dominant_sensor?.replace(/_/g, ' ') || '--'}</td>
                        <td className="num">{formatHours(item.rul_hours)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
        </div>
      )}

      {/* ---------------- Level 4 ---------------- */}
      {data.site_benchmark?.length > 0 && (
        <section className="card">
          <div className="card-header">
            <h2>Site benchmark</h2>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th className="num">Rank</th>
                  <th>Site</th>
                  <th className="num">Machines</th>
                  <th className="num">Avg OEE</th>
                  <th className="num">Downtime</th>
                  <th className="num">Cost</th>
                </tr>
              </thead>
              <tbody>
                {data.site_benchmark.map((row) => (
                  <tr key={row.site}>
                    <td className="num">{row.rank}</td>
                    <td className="primary">{row.site}</td>
                    <td className="num">{row.machine_count}</td>
                    <td className="num">{formatPercent(row.avg_oee, 1)}</td>
                    <td className="num">{formatHours(row.downtime_hours)}</td>
                    <td className="num">{formatCurrency(row.maintenance_cost)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
