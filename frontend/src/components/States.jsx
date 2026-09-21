import { LEVEL_NAMES, LEVEL_PRICING } from '../utils/constants';

export function Loading({ label = 'Loading…' }) {
  return <div className="state">{label}</div>;
}

export function ErrorState({ error, onRetry }) {
  return (
    <div className="state error">
      <p>{error?.message || 'Something went wrong.'}</p>
      {onRetry && (
        <button type="button" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

export function EmptyState({ title, hint }) {
  return (
    <div className="state">
      <strong>{title}</strong>
      {hint && <p className="muted small">{hint}</p>}
    </div>
  );
}

/**
 * Rendered in place of a feature the tenant has not unlocked.
 *
 * It states the level required and, when the maturity assessment is
 * available, exactly what the customer must send to get there.
 */
export function LockedPanel({ locked, featureName, requirements = [] }) {
  const required = locked?.requiredLevel;
  const current = locked?.currentLevel;

  return (
    <div className="locked-panel">
      <span className="level-chip">
        Level {required} · {LEVEL_NAMES[required]} · {LEVEL_PRICING[required]}
      </span>
      <h3>{featureName || 'This feature is not available yet'}</h3>
      <p>
        {locked?.message ||
          `Requires maturity Level ${required}. Your tenant is at Level ${current}.`}
      </p>
      {requirements.length > 0 && (
        <ul className="requirements">
          {requirements.map((requirement) => (
            <li key={requirement}>{requirement}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Small status pill. The label always carries the meaning, not the colour. */
export function Pill({ tone = 'neutral', children }) {
  return <span className={`pill ${tone}`}>{children}</span>;
}

/** Horizontal meter with a numeric readout beside it. */
export function Meter({ value, tone = 'neutral', label }) {
  const pct = Math.max(0, Math.min(100, value * 100));
  return (
    <div className="meter-row">
      <div className={`meter meter-${tone}`}>
        <span style={{ width: `${pct}%` }} />
      </div>
      <span className="value">{label}</span>
    </div>
  );
}
