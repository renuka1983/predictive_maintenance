import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { SimpleBars } from '../components/Charts';
import { ErrorState, Loading } from '../components/States';
import { useApi } from '../hooks/useApi';
import { useTenant } from '../hooks/useTenant';
import { formatAxisCurrency, formatCurrency, formatNumber } from '../utils/formatters';

/**
 * What-if simulator for a hypothetical stoppage.
 *
 * The point it makes: the cost of a machine going down is rarely the repair
 * bill - it is the output the rest of the line loses while it waits.
 */
export default function ImpactSimulator() {
  const { tenantId } = useTenant();
  const [machineId, setMachineId] = useState('');
  const [hours, setHours] = useState(4);
  const [submitted, setSubmitted] = useState(null);

  const machines = useApi(() => api.listMachines(tenantId, { limit: 200 }), [tenantId], {
    enabled: Boolean(tenantId),
  });

  useEffect(() => {
    const first = machines.data?.items?.[0];
    if (!machineId && first) setMachineId(first.id);
  }, [machines.data, machineId]);

  const result = useApi(
    () => api.simulate(tenantId, submitted.machineId, submitted.hours),
    [tenantId, submitted?.machineId, submitted?.hours],
    { enabled: Boolean(tenantId && submitted) },
  );

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h1>Impact simulator</h1>
          <p>Model the line-wide cost of taking one machine out of service.</p>
        </div>
      </div>

      <section className="card">
        <div className="control-row" style={{ marginBottom: 0 }}>
          <div className="field">
            <label htmlFor="sim-machine">Machine</label>
            <select
              id="sim-machine"
              value={machineId}
              onChange={(event) => setMachineId(event.target.value)}
            >
              {(machines.data?.items || []).map((machine) => (
                <option key={machine.id} value={machine.id}>
                  {machine.machine_code} — {machine.name}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="sim-hours">Downtime (hours)</label>
            <input
              id="sim-hours"
              type="number"
              min="0.5"
              max="720"
              step="0.5"
              value={hours}
              onChange={(event) => setHours(Number(event.target.value))}
            />
          </div>
          <button
            type="button"
            className="primary"
            style={{ alignSelf: 'flex-end' }}
            disabled={!machineId || hours <= 0}
            onClick={() => setSubmitted({ machineId, hours })}
          >
            Simulate
          </button>
        </div>
      </section>

      {submitted && result.loading && <Loading label="Simulating…" />}
      {result.error && <ErrorState error={result.error} onRetry={result.reload} />}

      {result.data && (
        <>
          <div className="grid cols-3">
            <div className="stat">
              <span className="stat-label">Direct loss</span>
              <span className="stat-value">
                {formatNumber(result.data.direct_lost_units)}
              </span>
              <span className="stat-sub">units on the stopped machine</span>
            </div>
            <div className="stat">
              <span className="stat-label">Cascade loss</span>
              <span className="stat-value">
                {formatNumber(result.data.cascade_lost_units)}
              </span>
              <span className="stat-sub">units lost elsewhere on the line</span>
            </div>
            <div className="stat">
              <span className="stat-label">Total cost</span>
              <span className="stat-value">{formatCurrency(result.data.total_cost)}</span>
              <span className="stat-sub">
                over {result.data.downtime_hours} hours
              </span>
            </div>
          </div>

          <section className="card">
            <div className="card-header">
              <h2>Lost revenue by machine</h2>
              <span className="muted small">{result.data.production_line || 'standalone'}</span>
            </div>
            <p className="card-note">
              Stations downstream starve for input; stations upstream block
              because work-in-progress has nowhere to go.
            </p>
            <SimpleBars
              data={result.data.affected_machines.map((node) => ({
                code: node.machine_code,
                revenue: node.lost_revenue,
              }))}
              xKey="code"
              valueKey="revenue"
              horizontal
              height={Math.max(180, 40 + result.data.affected_machines.length * 30)}
              valueFormatter={(value) => formatCurrency(value)}
              axisFormatter={formatAxisCurrency}
            />
          </section>

          <section className="card">
            <div className="card-header">
              <h2>Affected machines</h2>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th className="num">Pos</th>
                    <th>Machine</th>
                    <th>Effect</th>
                    <th className="num">Units lost</th>
                    <th className="num">Revenue lost</th>
                  </tr>
                </thead>
                <tbody>
                  {result.data.affected_machines.map((node) => (
                    <tr key={node.machine_id}>
                      <td className="num">{node.line_position ?? '--'}</td>
                      <td className="primary">{node.machine_code}</td>
                      <td>{node.impact_type.replace(/_/g, ' ')}</td>
                      <td className="num">{formatNumber(node.lost_units)}</td>
                      <td className="num">{formatCurrency(node.lost_revenue)}</td>
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
