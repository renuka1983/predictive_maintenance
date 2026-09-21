import { useState } from 'react';
import { api } from '../api/client';
import { SimpleBars } from '../components/Charts';
import { ErrorState, Loading, Pill } from '../components/States';
import { useApi } from '../hooks/useApi';
import { useTenant } from '../hooks/useTenant';
import {
  formatAxisCurrency,
  formatCurrency,
  formatHours,
  formatNumber,
  formatPercent,
} from '../utils/formatters';

/**
 * Level 4 multi-site rollup.
 *
 * Group-level rows are per-machine so a 40-machine plant and a 4-machine
 * plant compare fairly; the organisation totals are recomputed from raw
 * counts, and headline OEE is machine-weighted rather than a mean of means.
 */
export default function Portfolio() {
  const { tenantId } = useTenant();
  const [groupBy, setGroupBy] = useState('site');

  const { data, error, loading, reload } = useApi(
    () => api.portfolio(tenantId, groupBy),
    [tenantId, groupBy],
    { enabled: Boolean(tenantId) },
  );

  if (loading) return <Loading label="Rolling up the estate…" />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data) return null;

  const totals = data.totals;

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h1>Portfolio</h1>
          <p>
            {data.group_count} {groupBy === 'site' ? 'plants' : 'regions'} ·{' '}
            {totals.machine_count} machines · last {data.window_days} days
          </p>
        </div>
        <div className="field">
          <label htmlFor="group-by">Group by</label>
          <select
            id="group-by"
            value={groupBy}
            onChange={(event) => setGroupBy(event.target.value)}
          >
            <option value="site">Site</option>
            <option value="region">Region</option>
          </select>
        </div>
      </div>

      <div className="grid cols-4">
        <div className="stat">
          <span className="stat-label">Group OEE</span>
          <span className="stat-value">{formatPercent(totals.weighted_avg_oee, 1)}</span>
          <span className="stat-sub">weighted by machine count</span>
        </div>
        <div className="stat">
          <span className="stat-label">Maintenance spend</span>
          <span className="stat-value">{formatCurrency(totals.maintenance_cost)}</span>
          <span className="stat-sub">
            {formatCurrency(totals.cost_per_machine)} per machine
          </span>
        </div>
        <div className="stat">
          <span className="stat-label">Reactive ratio</span>
          <span className="stat-value">{formatPercent(totals.reactive_ratio)}</span>
          <span className="stat-sub">lower is better</span>
        </div>
        <div className="stat">
          <span className="stat-label">Downtime</span>
          <span className="stat-value">{formatHours(totals.downtime_hours)}</span>
          <span className="stat-sub">{totals.machines_down} machines down now</span>
        </div>
      </div>

      <div className="grid cols-2">
        <section className="card">
          <div className="card-header">
            <h2>Maintenance cost per machine</h2>
          </div>
          <p className="card-note">
            Normalised per machine, so plant size does not distort the comparison.
          </p>
          <SimpleBars
            data={data.groups.map((group) => ({
              name: group.display_name || group.name,
              cost: group.maintenance_cost_per_machine,
            }))}
            xKey="name"
            valueKey="cost"
            horizontal
            height={Math.max(180, 40 + data.groups.length * 34)}
            valueFormatter={(value) => formatCurrency(value)}
            axisFormatter={formatAxisCurrency}
          />
        </section>

        <section className="card">
          <div className="card-header">
            <h2>Average OEE</h2>
          </div>
          <p className="card-note">Mean effectiveness across each group's batches.</p>
          <SimpleBars
            data={data.groups.map((group) => ({
              name: group.display_name || group.name,
              oee: group.avg_oee,
            }))}
            xKey="name"
            valueKey="oee"
            horizontal
            height={Math.max(180, 40 + data.groups.length * 34)}
            valueFormatter={(value) => formatPercent(value, 1)}
            axisFormatter={(value) => formatPercent(value)}
          />
        </section>
      </div>

      <section className="card">
        <div className="card-header">
          <h2>{groupBy === 'site' ? 'Sites' : 'Regions'}</h2>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{groupBy === 'site' ? 'Site' : 'Region'}</th>
                {groupBy === 'site' && <th>Region</th>}
                <th className="num">Machines</th>
                <th className="num">OEE</th>
                <th className="num">Quality</th>
                <th className="num">Reactive</th>
                <th className="num">Downtime/mc</th>
                <th className="num">Cost/mc</th>
                {groupBy === 'site' && <th>Registry</th>}
              </tr>
            </thead>
            <tbody>
              {data.groups.map((group) => (
                <tr key={group.name}>
                  <td className="primary">{group.display_name || group.name}</td>
                  {groupBy === 'site' && (
                    <td>{group.region || <span className="muted">—</span>}</td>
                  )}
                  <td className="num">{formatNumber(group.machine_count)}</td>
                  <td className="num">{formatPercent(group.avg_oee, 1)}</td>
                  <td className="num">{formatPercent(group.quality_rate, 1)}</td>
                  <td className="num">{formatPercent(group.reactive_ratio)}</td>
                  <td className="num">
                    {formatNumber(group.downtime_hours_per_machine, 1)} h
                  </td>
                  <td className="num">
                    {formatCurrency(group.maintenance_cost_per_machine)}
                  </td>
                  {groupBy === 'site' && (
                    <td>
                      {group.is_registered ? (
                        <Pill tone="good">registered</Pill>
                      ) : (
                        <Pill tone="warning">unregistered</Pill>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
