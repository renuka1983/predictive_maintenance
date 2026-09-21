import { api } from '../api/client';
import { SimpleBars } from '../components/Charts';
import { ErrorState, Loading } from '../components/States';
import { useApi } from '../hooks/useApi';
import { useTenant } from '../hooks/useTenant';
import { formatCurrency, formatHours, formatNumber, formatPercent } from '../utils/formatters';

export default function Benchmark() {
  const { tenantId } = useTenant();
  const { data, error, loading, reload } = useApi(() => api.benchmark(tenantId), [tenantId], {
    enabled: Boolean(tenantId),
  });

  if (loading) return <Loading label="Comparing sites…" />;
  if (error) return <ErrorState error={error} onRetry={reload} />;

  const rows = data || [];

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h1>Site benchmarking</h1>
          <p>Sites ranked by average OEE over the last 90 days.</p>
        </div>
      </div>

      <section className="card">
        <div className="card-header">
          <h2>Average OEE by site</h2>
        </div>
        <SimpleBars
          data={rows.map((row) => ({ site: row.site, oee: row.avg_oee }))}
          xKey="site"
          valueKey="oee"
          height={Math.max(200, 40 + rows.length * 34)}
          valueFormatter={(value) => formatPercent(value, 1)}
          axisFormatter={(value) => formatPercent(value)}
        />
      </section>

      <section className="card">
        <div className="card-header">
          <h2>Site comparison</h2>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th className="num">Rank</th>
                <th>Site</th>
                <th className="num">Machines</th>
                <th className="num">Events</th>
                <th className="num">Downtime</th>
                <th className="num">Cost</th>
                <th className="num">Cost/machine</th>
                <th className="num">Avg OEE</th>
                <th className="num">Units</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.site}>
                  <td className="num">{row.rank}</td>
                  <td className="primary">{row.site}</td>
                  <td className="num">{row.machine_count}</td>
                  <td className="num">{row.maintenance_events}</td>
                  <td className="num">{formatHours(row.downtime_hours)}</td>
                  <td className="num">{formatCurrency(row.maintenance_cost)}</td>
                  <td className="num">{formatCurrency(row.cost_per_machine)}</td>
                  <td className="num">{formatPercent(row.avg_oee, 1)}</td>
                  <td className="num">{formatNumber(row.produced_units)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
