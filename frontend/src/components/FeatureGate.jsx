import { useTenant } from '../hooks/useTenant';
import { LockedPanel } from './States';

const FEATURE_META = {
  production_tracking: { level: 2, name: 'Production Tracking' },
  failure_risk_scoring: { level: 2, name: 'Failure Risk Scoring' },
  cascade_impact_analysis: { level: 2, name: 'Cascade Impact Analysis' },
  impact_simulator: { level: 2, name: 'Downtime Impact Simulator' },
  roi_analysis: { level: 2, name: 'ROI Analysis' },
  sensor_telemetry: { level: 3, name: 'Sensor Telemetry' },
  realtime_monitoring: { level: 3, name: 'Real-time Monitoring' },
  anomaly_detection: { level: 3, name: 'Anomaly Detection' },
  rul_prediction: { level: 3, name: 'Remaining Useful Life' },
  benchmarking: { level: 4, name: 'Site Benchmarking' },
};

/**
 * Renders `children` only when the tenant has unlocked `feature`.
 *
 * This is a convenience for whole pages. Individual data calls still get a
 * 403 from the backend, which is the authoritative check - this component
 * only avoids a pointless request.
 */
export default function FeatureGate({ feature, children, requirements = [] }) {
  const { hasFeature, level, features } = useTenant();

  if (!features) return null;
  if (hasFeature(feature)) return children;

  const meta = FEATURE_META[feature] || { level: '?', name: feature };
  return (
    <LockedPanel
      featureName={meta.name}
      requirements={requirements}
      locked={{
        requiredLevel: meta.level,
        currentLevel: level,
        message: `'${meta.name}' unlocks at maturity Level ${meta.level}. Your tenant is at Level ${level}.`,
      }}
    />
  );
}
