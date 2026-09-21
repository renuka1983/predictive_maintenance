import { NavLink } from 'react-router-dom';
import { useTenant } from '../hooks/useTenant';
import { LEVEL_NAMES } from '../utils/constants';

/**
 * Sidebar navigation.
 *
 * Pages whose feature is locked stay visible but disabled, with the level
 * they need shown alongside - the upgrade path is part of the product, so
 * hiding locked capabilities entirely would defeat it.
 */
const SECTIONS = [
  {
    label: 'Overview',
    items: [{ to: '/', label: 'Dashboard', end: true }],
  },
  {
    label: 'Level 1 · Maintenance',
    items: [
      { to: '/machines', label: 'Machines', feature: 'machine_registry' },
      { to: '/maintenance', label: 'Maintenance', feature: 'maintenance_history' },
      { to: '/reliability', label: 'Reliability', feature: 'weibull_reliability' },
    ],
  },
  {
    label: 'Level 2 · Predictive',
    items: [
      { to: '/production', label: 'Production Lines', feature: 'production_tracking' },
      { to: '/risk', label: 'Risk Analysis', feature: 'failure_risk_scoring' },
      { to: '/simulator', label: 'Impact Simulator', feature: 'impact_simulator' },
    ],
  },
  {
    label: 'Level 3 · Real-time',
    items: [
      { to: '/monitoring', label: 'Live Monitoring', feature: 'realtime_monitoring' },
      { to: '/telemetry', label: 'Sensor Telemetry', feature: 'sensor_telemetry' },
    ],
  },
  {
    label: 'Level 4 · Enterprise',
    items: [
      { to: '/portfolio', label: 'Portfolio', feature: 'multi_site' },
      { to: '/benchmark', label: 'Site Benchmarking', feature: 'benchmarking' },
      { to: '/fleet', label: 'Fleet Comparison', feature: 'fleet_comparison' },
      { to: '/sites', label: 'Site Registry', feature: 'site_registry' },
    ],
  },
  {
    label: 'Account',
    items: [{ to: '/settings', label: 'Settings & Maturity' }],
  },
];

const FEATURE_LEVEL = {
  machine_registry: 1,
  maintenance_history: 1,
  weibull_reliability: 1,
  production_tracking: 2,
  failure_risk_scoring: 2,
  impact_simulator: 2,
  realtime_monitoring: 3,
  sensor_telemetry: 3,
  benchmarking: 4,
  multi_site: 4,
  fleet_comparison: 4,
  site_registry: 4,
};

export default function Navigation() {
  const { tenants, tenantId, setTenantId, hasFeature, level, features } = useTenant();

  return (
    <aside className="sidebar">
      <div className="brand">
        <strong>Manufacturing AI</strong>
        <span>
          Level {level} · {LEVEL_NAMES[level]}
        </span>
      </div>

      <div className="field" style={{ padding: '0 8px' }}>
        <label htmlFor="tenant-select">Tenant</label>
        <select
          id="tenant-select"
          value={tenantId}
          onChange={(event) => setTenantId(event.target.value)}
        >
          {tenants.length === 0 && <option value="">No tenants</option>}
          {tenants.map((tenant) => (
            <option key={tenant.id} value={tenant.slug}>
              {tenant.name}
            </option>
          ))}
        </select>
      </div>

      {SECTIONS.map((section) => (
        <nav className="nav-group" key={section.label}>
          <span className="nav-group-label">{section.label}</span>
          {section.items.map((item) => {
            // Until features load, treat everything as available so the nav
            // does not flash a locked state on first paint.
            const locked = item.feature && features && !hasFeature(item.feature);
            if (locked) {
              return (
                <span className="nav-item locked" key={item.to} aria-disabled="true">
                  {item.label}
                  <span className="lock-badge">L{FEATURE_LEVEL[item.feature]}</span>
                </span>
              );
            }
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
              >
                {item.label}
              </NavLink>
            );
          })}
        </nav>
      ))}
    </aside>
  );
}
