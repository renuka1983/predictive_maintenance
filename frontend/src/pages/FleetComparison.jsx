import { useMemo, useState } from 'react';
import { api } from '../api/client';
import { SimpleBars } from '../components/Charts';
import { ErrorState, Loading, Pill } from '../components/States';
import { useApi } from '../hooks/useApi';
import { useTenant } from '../hooks/useTenant';
import {
  formatAxisCurrency,
  formatCurrency,
  formatNumber,
  formatPercent,
} from '../utils/formatters';

/**
 * Level 4 fleet comparison.
 *
 * Site-level benchmarking can hide the cause: a plant may look expensive only
 * because it runs more of one troublesome asset class. Holding the machine
 * type constant and varying the site separates "this plant runs worse" from
 * "this plant runs harder equipment".
 */
export default function FleetComparison() {
  const { tenantId } = useTenant();
  const [machineType, setMachineType] = useState('');

  const { data, error, loading, reload } = useApi(
    () => api.fleet(tenantId, machineType || undefined),
    [tenantId, machineType],
    { enabled: Boolean(tenantId) },
  );

  const allTypes = useApi(() => api.fleet(tenantId), [tenantId], {
    enabled: Boolean(tenantId),
  });

  const typeOptions = useMemo(
    () => [...new Set((allTypes.data || []).map((row) => row.machine_type))].sort(),
    [allTypes.data],
  );

  const grouped = useMemo(() => {
    const byType = new Map();
    for (const row of data || []) {
      if (!byType.has(row.machine_type)) byType.set(row.machine_type, []);
      byType.get(row.machine_type).push(row);
    }
    return [...byType.entries()];
  }, [data]);

  if (loading) return <Loading label="Comparing the fleet…" />;
  if (error) return <ErrorState error={error} onRetry={reload} />;

  if (!data?.length) {
    return (
      <div className="state">
        <strong>No fleet data</strong>
        <p className="muted small">
          Set a machine_type on your machines to compare asset classes across sites.
        </p>
      </div>
    );
  }

  // The headline insight: classes where one site costs far more than another
  // running the same equipment.
  const outliers = (data || [])
    .filter((row) => row.is_worst_in_class && (row.cost_ratio_vs_best || 0) > 1.2)
    .sort((a, b) => (b.cost_ratio_vs_best || 0) - (a.cost_ratio_vs_best || 0));

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h1>Fleet comparison</h1>
          <p>The same class of asset, compared across every site.</p>
        </div>
        <div className="field">
          <label htmlFor="asset-type">Asset class</label>
          <select
            id="asset-type"
            value={machineType}
            onChange={(event) => setMachineType(event.target.value)}
          >
            <option value="">All classes</option>
            {typeOptions.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
        </div>
      </div>

      {outliers.length > 0 && (
        <section className="card">
          <div className="card-header">
            <h2>Same equipment, different outcome</h2>
          </div>
          <p className="card-note">
            Asset classes where one site spends materially more than another
            running identical equipment — the gap is the operation, not the kit.
          </p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Asset class</th>
                  <th>Worst site</th>
                  <th className="num">Cost per machine</th>
                  <th className="num">vs best site</th>
                </tr>
              </thead>
              <tbody>
                {outliers.slice(0, 6).map((row) => (
                  <tr key={`${row.machine_type}-${row.site}`}>
                    <td className="primary">{row.machine_type}</td>
                    <td>{row.site}</td>
                    <td className="num">
                      {formatCurrency(row.maintenance_cost_per_machine)}
                    </td>
                    <td className="num">
                      <Pill tone={row.cost_ratio_vs_best >= 2 ? 'critical' : 'warning'}>
                        {formatNumber(row.cost_ratio_vs_best, 2)}×
                      </Pill>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {grouped.map(([type, rows]) => (
        <section className="card" key={type}>
          <div className="card-header">
            <h2>{type}</h2>
            <span className="muted small">
              {rows.length} {rows.length === 1 ? 'site' : 'sites'}
            </span>
          </div>
          <SimpleBars
            data={rows.map((row) => ({
              site: row.site,
              cost: row.maintenance_cost_per_machine,
            }))}
            xKey="site"
            valueKey="cost"
            horizontal
            height={Math.max(140, 40 + rows.length * 32)}
            valueFormatter={(value) => formatCurrency(value)}
            axisFormatter={formatAxisCurrency}
          />
          <div className="table-wrap" style={{ marginTop: 10 }}>
            <table>
              <thead>
                <tr>
                  <th>Site</th>
                  <th className="num">Machines</th>
                  <th className="num">Reactive</th>
                  <th className="num">Downtime/mc</th>
                  <th className="num">Cost/mc</th>
                  <th className="num">vs best</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.site}>
                    <td className="primary">{row.site}</td>
                    <td className="num">{row.machine_count}</td>
                    <td className="num">{formatPercent(row.reactive_ratio)}</td>
                    <td className="num">
                      {formatNumber(row.downtime_hours_per_machine, 1)} h
                    </td>
                    <td className="num">
                      {formatCurrency(row.maintenance_cost_per_machine)}
                    </td>
                    <td className="num">
                      {row.cost_ratio_vs_best
                        ? `${formatNumber(row.cost_ratio_vs_best, 2)}×`
                        : '--'}
                    </td>
                    <td>
                      {row.is_best_in_class && <Pill tone="good">best</Pill>}
                      {row.is_worst_in_class && <Pill tone="critical">worst</Pill>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}
    </div>
  );
}
