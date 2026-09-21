import { useState } from 'react';
import { api } from '../api/client';
import { ErrorState, Loading, Meter, Pill } from '../components/States';
import { useApi } from '../hooks/useApi';
import { useTenant } from '../hooks/useTenant';
import { LEVEL_NAMES, LEVEL_PRICING } from '../utils/constants';
import { formatDate, formatNumber } from '../utils/formatters';

/**
 * Maturity detail and feature administration.
 *
 * This is where the product explains itself: the score breakdown says why a
 * tenant is at its level, and the upgrade path says exactly what to send to
 * move up.
 */
export default function Settings() {
  const { tenantId, tenant, refreshFeatures } = useTenant();
  const [busy, setBusy] = useState(false);

  const maturity = useApi(() => api.getMaturity(tenantId), [tenantId], {
    enabled: Boolean(tenantId),
  });
  const features = useApi(() => api.listFeatures(tenantId), [tenantId], {
    enabled: Boolean(tenantId),
  });

  const runAssessment = async () => {
    setBusy(true);
    try {
      await api.assess(tenantId);
      await Promise.all([maturity.reload(), features.reload(), refreshFeatures()]);
    } finally {
      setBusy(false);
    }
  };

  const toggleFeature = async (key, enabled) => {
    setBusy(true);
    try {
      await api.setFeature(tenantId, key, enabled);
      await Promise.all([features.reload(), refreshFeatures()]);
    } finally {
      setBusy(false);
    }
  };

  if (maturity.loading) return <Loading label="Loading maturity assessment…" />;
  if (maturity.error) return <ErrorState error={maturity.error} onRetry={maturity.reload} />;

  const data = maturity.data;
  const upgrade = data.upgrade_path;

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h1>Settings &amp; maturity</h1>
          <p>
            {tenant?.name} · {tenant?.industry || 'industry not set'} · last assessed{' '}
            {formatDate(tenant?.last_assessed_at)}
          </p>
        </div>
        <button type="button" className="primary" onClick={runAssessment} disabled={busy}>
          {busy ? 'Assessing…' : 'Re-run assessment'}
        </button>
      </div>

      <div className="grid cols-3">
        <div className="stat">
          <span className="stat-label">Maturity level</span>
          <span className="stat-value">{data.level}</span>
          <span className="stat-sub">{LEVEL_NAMES[data.level]}</span>
        </div>
        <div className="stat">
          <span className="stat-label">Score</span>
          <span className="stat-value">{formatNumber(data.score, 1)}</span>
          <span className="stat-sub">out of 100</span>
        </div>
        <div className="stat">
          <span className="stat-label">Plan</span>
          <span className="stat-value">{LEVEL_PRICING[data.level]}</span>
          <span className="stat-sub">
            {upgrade.next_level != null
              ? `Next: Level ${upgrade.next_level} at ${LEVEL_PRICING[upgrade.next_level]}`
              : 'Highest tier'}
          </span>
        </div>
      </div>

      <section className="card">
        <div className="card-header">
          <h2>Score breakdown</h2>
          <span className="muted small">four dimensions, 25 points each</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Dimension</th>
                <th>Detail</th>
                <th className="num">Score</th>
              </tr>
            </thead>
            <tbody>
              {data.dimensions.map((dimension) => (
                <tr key={dimension.name}>
                  <td className="primary">{dimension.name.replace(/_/g, ' ')}</td>
                  <td>{dimension.detail}</td>
                  <td className="num">
                    <Meter
                      value={dimension.score / dimension.max_score}
                      tone={
                        dimension.score >= 20
                          ? 'good'
                          : dimension.score >= 12
                            ? 'warning'
                            : 'serious'
                      }
                      label={`${formatNumber(dimension.score, 1)}/25`}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {upgrade.next_level != null && (
        <section className="card">
          <div className="card-header">
            <h2>Path to Level {upgrade.next_level}</h2>
            <span className="muted small">{LEVEL_NAMES[upgrade.next_level]}</span>
          </div>
          <ul className="requirements" style={{ margin: '8px 0 14px' }}>
            {upgrade.requirements.map((requirement) => (
              <li key={requirement}>{requirement}</li>
            ))}
          </ul>
          <h3 className="muted" style={{ marginBottom: 8 }}>
            Unlocks
          </h3>
          <div className="inline-list">
            {upgrade.unlocks.map((unlock) => (
              <span className="tag" key={unlock}>
                {unlock}
              </span>
            ))}
          </div>
        </section>
      )}

      <section className="card">
        <div className="card-header">
          <h2>Features</h2>
          <span className="muted small">manual overrides survive re-assessment</span>
        </div>
        {features.loading ? (
          <Loading />
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Feature</th>
                  <th>Description</th>
                  <th className="num">Level</th>
                  <th>Status</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {[
                  ...(features.data?.enabled || []).map((f) => ({ ...f, on: true })),
                  ...(features.data?.locked || []).map((f) => ({ ...f, on: false })),
                ]
                  .sort((a, b) => a.required_level - b.required_level)
                  .map((feature) => (
                    <tr key={feature.feature_key}>
                      <td className="primary">{feature.name}</td>
                      <td>{feature.description}</td>
                      <td className="num">{feature.required_level}</td>
                      <td>
                        <Pill tone={feature.on ? 'good' : 'neutral'}>
                          {feature.on ? 'enabled' : 'locked'}
                        </Pill>
                      </td>
                      <td>
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => toggleFeature(feature.feature_key, !feature.on)}
                        >
                          {feature.on ? 'Revoke' : 'Grant'}
                        </button>
                      </td>
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
