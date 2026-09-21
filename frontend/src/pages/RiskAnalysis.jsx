import { api } from '../api/client';
import { SimpleBars } from '../components/Charts';
import { ErrorState, Loading, Meter, Pill } from '../components/States';
import { useApi } from '../hooks/useApi';
import { useTenant } from '../hooks/useTenant';
import { formatCurrency, formatHours, formatPercent, statusTone } from '../utils/formatters';

const TONE_VAR = {
  good: 'var(--status-good)',
  warning: 'var(--status-warning)',
  serious: 'var(--status-serious)',
  critical: 'var(--status-critical)',
};

export default function RiskAnalysis() {
  const { tenantId } = useTenant();
  const risk = useApi(() => api.risk(tenantId, { horizon_days: 30 }), [tenantId], {
    enabled: Boolean(tenantId),
  });
  const roi = useApi(() => api.roi(tenantId), [tenantId], { enabled: Boolean(tenantId) });

  if (risk.loading) return <Loading label="Scoring failure risk…" />;
  if (risk.error) return <ErrorState error={risk.error} onRetry={risk.reload} />;

  const scores = risk.data || [];
  const model = scores[0];

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h1>Risk analysis</h1>
          <p>
            Probability of failure in the next 30 days
            {model && ` · ${model.model_used.replace(/_/g, ' ')} (${model.confidence} confidence)`}
          </p>
        </div>
      </div>

      {roi.data && (
        <div className="grid cols-3">
          <div className="stat">
            <span className="stat-label">Reactive cost</span>
            <span className="stat-value">{formatCurrency(roi.data.reactive_cost)}</span>
            <span className="stat-sub">repairs plus lost production</span>
          </div>
          <div className="stat">
            <span className="stat-label">Estimated annual savings</span>
            <span className="stat-value">
              {formatCurrency(roi.data.estimated_annual_savings)}
            </span>
            <span className="stat-sub">if preventable failures are avoided</span>
          </div>
          <div className="stat">
            <span className="stat-label">Downtime avoided</span>
            <span className="stat-value">
              {formatHours(roi.data.downtime_hours_avoided)}
            </span>
            <span className="stat-sub">per year</span>
          </div>
        </div>
      )}

      <section className="card">
        <div className="card-header">
          <h2>Failure probability by machine</h2>
        </div>
        <p className="card-note">
          Colour marks the risk band. Bands: critical ≥ 70%, high ≥ 45%, medium ≥ 20%.
        </p>
        <SimpleBars
          data={scores.map((score) => ({
            code: score.machine_code,
            risk: score.risk_score,
            tone: statusTone(score.risk_band),
          }))}
          xKey="code"
          valueKey="risk"
          height={Math.max(200, 40 + scores.length * 28)}
          horizontal
          valueFormatter={(value) => formatPercent(value, 1)}
          axisFormatter={(value) => formatPercent(value)}
          toneFor={(row) => TONE_VAR[row.tone]}
        />
      </section>

      <section className="card">
        <div className="card-header">
          <h2>Risk drivers</h2>
        </div>
        <p className="card-note">
          The factors contributing most to each machine's score.
        </p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Machine</th>
                <th>Band</th>
                <th className="num">Risk</th>
                <th>Top drivers</th>
              </tr>
            </thead>
            <tbody>
              {scores.map((score) => (
                <tr key={score.machine_id}>
                  <td className="primary">{score.machine_code}</td>
                  <td>
                    <Pill tone={statusTone(score.risk_band)}>{score.risk_band}</Pill>
                  </td>
                  <td className="num">
                    <Meter
                      value={score.risk_score}
                      tone={statusTone(score.risk_band)}
                      label={formatPercent(score.risk_score)}
                    />
                  </td>
                  <td>
                    <div className="inline-list">
                      {score.drivers.slice(0, 3).map((driver) => (
                        <span className="tag" key={driver.factor}>
                          {driver.factor.replace(/_/g, ' ')}
                        </span>
                      ))}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
