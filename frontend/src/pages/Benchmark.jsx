import { api } from '../api/client';
import { SimpleBars } from '../components/Charts';
import { ErrorState, Loading, Meter, Pill } from '../components/States';
import { useApi } from '../hooks/useApi';
import { useTenant } from '../hooks/useTenant';
import {
  formatAxisCurrency,
  formatCurrency,
  formatHours,
  formatNumber,
  formatPercent,
} from '../utils/formatters';

/** Composite percentile bands. 1.0 is best-in-class for every metric. */
const scoreTone = (score) =>
  score >= 0.75 ? 'good' : score >= 0.5 ? 'warning' : score >= 0.25 ? 'serious' : 'critical';

const TONE_VAR = {
  good: 'var(--status-good)',
  warning: 'var(--status-warning)',
  serious: 'var(--status-serious)',
  critical: 'var(--status-critical)',
};

/** Metrics where a smaller number is better, for the leader table. */
const formatMetric = (metric, value) => {
  if (value === null || value === undefined) return '--';
  if (metric === 'avg_oee' || metric === 'reactive_ratio') {
    return formatPercent(value, 1);
  }
  if (metric === 'maintenance_cost_per_machine') return formatCurrency(value);
  if (metric === 'mtbf_hours') return formatHours(value);
  if (metric === 'downtime_hours_per_machine') return `${formatNumber(value, 1)} h`;
  return formatNumber(value, 1);
};

export default function Benchmark() {
  const { tenantId } = useTenant();
  const { data, error, loading, reload } = useApi(
    () => api.benchmark(tenantId),
    [tenantId],
    { enabled: Boolean(tenantId) },
  );

  if (loading) return <Loading label="Comparing sites…" />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data) return null;

  const { sites, metric_leaders: leaders, opportunity } = data;

  if (!sites.length) {
    return (
      <div className="state">
        <strong>Nothing to benchmark yet</strong>
        <p className="muted small">Register machines against at least two sites.</p>
      </div>
    );
  }

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h1>Site benchmarking</h1>
          <p>
            {data.site_count} sites ranked across {Object.keys(leaders).length} metrics ·
            last {data.window_days} days
          </p>
        </div>
      </div>

      {opportunity && (
        <section className="card">
          <div className="card-header">
            <h2>Improvement opportunity</h2>
            <span className="muted small">
              benchmark: {opportunity.benchmark_site}
            </span>
          </div>
          <p className="card-note">
            What it is worth bringing every plant up to your own best performer —
            a target already proven achievable inside your estate.
          </p>
          <div className="grid cols-3">
            <div className="stat">
              <span className="stat-label">Annualised saving</span>
              <span className="stat-value">
                {formatCurrency(opportunity.annualised_saving)}
              </span>
              <span className="stat-sub">
                vs {formatCurrency(opportunity.benchmark_cost_per_machine)} per machine
              </span>
            </div>
            <div className="stat">
              <span className="stat-label">Downtime recoverable</span>
              <span className="stat-value">
                {formatNumber(opportunity.annualised_downtime_hours)} h
              </span>
              <span className="stat-sub">per year across the estate</span>
            </div>
            <div className="stat">
              <span className="stat-label">Biggest gap</span>
              <span className="stat-value">
                {opportunity.worst_offenders[0]?.site || '--'}
              </span>
              <span className="stat-sub">
                {opportunity.worst_offenders[0]
                  ? `${formatCurrency(opportunity.worst_offenders[0].cost_gap)} over the window`
                  : 'all sites at benchmark'}
              </span>
            </div>
          </div>

          {opportunity.worst_offenders.length > 0 && (
            <>
              <h3 className="muted" style={{ margin: '14px 0 8px' }}>
                Cost gap to benchmark
              </h3>
              <SimpleBars
                data={opportunity.worst_offenders.map((row) => ({
                  site: row.site,
                  gap: row.cost_gap,
                }))}
                xKey="site"
                valueKey="gap"
                horizontal
                height={Math.max(140, 40 + opportunity.worst_offenders.length * 32)}
                valueFormatter={(value) => formatCurrency(value)}
                axisFormatter={formatAxisCurrency}
              />
            </>
          )}

          <ul className="requirements" style={{ marginTop: 12 }}>
            {opportunity.assumptions.map((assumption) => (
              <li key={assumption}>{assumption}</li>
            ))}
          </ul>
        </section>
      )}

      <section className="card">
        <div className="card-header">
          <h2>Composite score by site</h2>
        </div>
        <p className="card-note">
          Mean percentile across every metric, direction-normalised so 100% is
          best-in-class whether the metric is one to maximise or minimise.
        </p>
        <SimpleBars
          data={sites.map((site) => ({
            site: site.display_name || site.site,
            score: site.composite_score,
            tone: scoreTone(site.composite_score),
          }))}
          xKey="site"
          valueKey="score"
          height={Math.max(180, 40 + sites.length * 34)}
          valueFormatter={(value) => formatPercent(value)}
          axisFormatter={(value) => formatPercent(value)}
          toneFor={(row) => TONE_VAR[row.tone]}
          showValueLabels
        />
      </section>

      <section className="card">
        <div className="card-header">
          <h2>Ranking</h2>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th className="num">Rank</th>
                <th>Site</th>
                <th>Region</th>
                <th className="num">Machines</th>
                <th className="num">OEE</th>
                <th className="num">MTBF</th>
                <th className="num">Downtime/mc</th>
                <th className="num">Cost/mc</th>
                <th className="num">Composite</th>
              </tr>
            </thead>
            <tbody>
              {sites.map((site) => (
                <tr key={site.site}>
                  <td className="num">{site.rank}</td>
                  <td className="primary">{site.display_name || site.site}</td>
                  <td>{site.region || <span className="muted">—</span>}</td>
                  <td className="num">{site.machine_count}</td>
                  <td className="num">{formatPercent(site.avg_oee, 1)}</td>
                  <td className="num">{formatHours(site.mtbf_hours)}</td>
                  <td className="num">
                    {formatNumber(site.downtime_hours_per_machine, 1)} h
                  </td>
                  <td className="num">
                    {formatCurrency(site.maintenance_cost_per_machine)}
                  </td>
                  <td className="num">
                    <Meter
                      value={site.composite_score}
                      tone={scoreTone(site.composite_score)}
                      label={formatPercent(site.composite_score)}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card">
        <div className="card-header">
          <h2>Metric leaders</h2>
        </div>
        <p className="card-note">
          Best and worst performer per metric, with the estate median for context.
        </p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Metric</th>
                <th>Best</th>
                <th className="num">Value</th>
                <th>Worst</th>
                <th className="num">Value</th>
                <th className="num">Median</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(leaders).map(([metric, leader]) => (
                <tr key={metric}>
                  <td className="primary">
                    {leader.label}{' '}
                    <Pill tone="neutral">
                      {leader.higher_is_better ? 'higher better' : 'lower better'}
                    </Pill>
                  </td>
                  <td>{leader.best_site}</td>
                  <td className="num">{formatMetric(metric, leader.best_value)}</td>
                  <td>{leader.worst_site}</td>
                  <td className="num">{formatMetric(metric, leader.worst_value)}</td>
                  <td className="num">{formatMetric(metric, leader.median)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
