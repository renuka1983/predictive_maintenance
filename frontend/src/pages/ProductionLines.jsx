import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { SimpleBars } from '../components/Charts';
import { ErrorState, Loading, Pill } from '../components/States';
import { useApi } from '../hooks/useApi';
import { useTenant } from '../hooks/useTenant';
import {
  formatNumber,
  formatPercent,
  machineTone,
} from '../utils/formatters';

/** OEE bands used to colour stations; world-class OEE is ~85%. */
const oeeTone = (oee) =>
  oee >= 0.85 ? 'good' : oee >= 0.7 ? 'warning' : oee >= 0.5 ? 'serious' : 'critical';

const TONE_VAR = {
  good: 'var(--status-good)',
  warning: 'var(--status-warning)',
  serious: 'var(--status-serious)',
  critical: 'var(--status-critical)',
};

export default function ProductionLines() {
  const { tenantId } = useTenant();
  const [line, setLine] = useState('');

  const lines = useApi(() => api.listLines(tenantId), [tenantId], {
    enabled: Boolean(tenantId),
  });

  useEffect(() => {
    if (!line && lines.data?.length) setLine(lines.data[0]);
  }, [lines.data, line]);

  const view = useApi(() => api.lineView(tenantId, line), [tenantId, line], {
    enabled: Boolean(tenantId && line),
  });

  if (lines.loading) return <Loading label="Loading production lines…" />;
  if (lines.error) return <ErrorState error={lines.error} onRetry={lines.reload} />;
  if (!lines.data?.length) {
    return (
      <div className="state">
        No production lines configured. Set a production_line on your machines.
      </div>
    );
  }

  const data = view.data;

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h1>Production lines</h1>
          <p>Station-by-station effectiveness in flow order, last 30 days.</p>
        </div>
        <div className="field">
          <label htmlFor="line">Line</label>
          <select id="line" value={line} onChange={(event) => setLine(event.target.value)}>
            {lines.data.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </div>
      </div>

      {view.loading && <Loading />}
      {view.error && <ErrorState error={view.error} onRetry={view.reload} />}

      {data && (
        <>
          <div className="grid cols-3">
            <div className="stat">
              <span className="stat-label">Line OEE</span>
              <span className="stat-value">{formatPercent(data.line_oee, 1)}</span>
              <span className="stat-sub">mean across active stations</span>
            </div>
            <div className="stat">
              <span className="stat-label">Units produced</span>
              <span className="stat-value">{formatNumber(data.total_produced_units)}</span>
              <span className="stat-sub">last {data.window_days} days</span>
            </div>
            <div className="stat">
              <span className="stat-label">Downtime</span>
              <span className="stat-value">
                {formatNumber(data.total_downtime_minutes / 60, 1)} h
              </span>
              <span className="stat-sub">across all stations</span>
            </div>
          </div>

          <section className="card">
            <div className="card-header">
              <h2>OEE by station</h2>
              <span className="muted small">bottleneck marked below</span>
            </div>
            <p className="card-note">
              Colour marks the OEE band; the bottleneck is the lowest-OEE station
              that ran, and it caps what the whole line can deliver.
            </p>
            <SimpleBars
              data={data.stations.map((station) => ({
                code: station.machine_code,
                oee: station.oee,
                tone: oeeTone(station.oee),
              }))}
              xKey="code"
              valueKey="oee"
              height={220}
              valueFormatter={(value) => formatPercent(value, 1)}
              axisFormatter={(value) => formatPercent(value)}
              toneFor={(row) => TONE_VAR[row.tone]}
            />
          </section>

          <section className="card">
            <div className="card-header">
              <h2>Stations</h2>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th className="num">Pos</th>
                    <th>Machine</th>
                    <th>Status</th>
                    <th className="num">OEE</th>
                    <th className="num">Yield</th>
                    <th className="num">Units</th>
                    <th className="num">Downtime</th>
                    <th>Role</th>
                  </tr>
                </thead>
                <tbody>
                  {data.stations.map((station) => (
                    <tr key={station.machine_id}>
                      <td className="num">{station.line_position ?? '--'}</td>
                      <td className="primary">{station.machine_code}</td>
                      <td>
                        <Pill tone={machineTone(station.status)}>{station.status}</Pill>
                      </td>
                      <td className="num">{formatPercent(station.oee, 1)}</td>
                      <td className="num">{formatPercent(station.yield_rate, 1)}</td>
                      <td className="num">{formatNumber(station.produced_units)}</td>
                      <td className="num">
                        {formatNumber(station.downtime_minutes / 60, 1)} h
                      </td>
                      <td>
                        {station.is_bottleneck ? (
                          <Pill tone="critical">bottleneck</Pill>
                        ) : (
                          <span className="muted">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
