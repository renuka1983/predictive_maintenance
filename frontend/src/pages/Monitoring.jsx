import { api } from '../api/client';
import { ErrorState, Loading, Pill } from '../components/States';
import { useApi } from '../hooks/useApi';
import { useTenant } from '../hooks/useTenant';
import { POLL_INTERVAL_MS, SENSOR_UNITS } from '../utils/constants';
import { formatHours, formatNumber, formatTime, statusTone } from '../utils/formatters';

/**
 * Level 3 live plant view.
 *
 * Polls the backend on an interval; background refreshes keep the previous
 * frame on screen so the page never blanks between ticks.
 */
export default function Monitoring() {
  const { tenantId } = useTenant();

  const snapshot = useApi(() => api.latestReadings(tenantId), [tenantId], {
    enabled: Boolean(tenantId),
    pollMs: POLL_INTERVAL_MS,
  });
  const anomalies = useApi(() => api.anomalies(tenantId, 24), [tenantId], {
    enabled: Boolean(tenantId),
    pollMs: POLL_INTERVAL_MS,
  });
  const rul = useApi(() => api.rul(tenantId), [tenantId], { enabled: Boolean(tenantId) });

  if (snapshot.loading) return <Loading label="Connecting to plant floor…" />;
  if (snapshot.error) return <ErrorState error={snapshot.error} onRetry={snapshot.reload} />;

  const machines = snapshot.data || [];
  const rulByMachine = Object.fromEntries(
    (rul.data || []).map((item) => [item.machine_id, item]),
  );
  const anomalyCounts = (anomalies.data?.anomalies || []).reduce((acc, event) => {
    acc[event.machine_id] = (acc[event.machine_id] || 0) + 1;
    return acc;
  }, {});

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h1>Live monitoring</h1>
          <p>
            {machines.length} instrumented machines · refreshing every{' '}
            {POLL_INTERVAL_MS / 1000}s
          </p>
        </div>
        <div className="inline-list">
          <span className="tag">
            {anomalies.data?.anomaly_count ?? 0} anomalies in 24h
          </span>
        </div>
      </div>

      <div className="grid cols-3">
        {machines.map((machine) => {
          const prediction = rulByMachine[machine.machine_id];
          const anomalyCount = anomalyCounts[machine.machine_id] || 0;
          const tone =
            anomalyCount > 3 ? 'critical' : anomalyCount > 0 ? 'warning' : 'good';

          return (
            <section className="card" key={machine.machine_id}>
              <div className="card-header">
                <h2>{machine.machine_code}</h2>
                <Pill tone={tone}>
                  {anomalyCount === 0 ? 'nominal' : `${anomalyCount} anomalies`}
                </Pill>
              </div>
              <p className="card-note">
                Updated {formatTime(machine.captured_at)}
                {prediction?.rul_hours != null &&
                  ` · RUL ${formatHours(prediction.rul_hours)}`}
              </p>
              <div className="table-wrap">
                <table>
                  <tbody>
                    {machine.readings.map((reading) => (
                      <tr key={reading.id}>
                        <td className="primary">
                          {reading.sensor_type.replace(/_/g, ' ')}
                        </td>
                        <td className="num">
                          {formatNumber(reading.value, 2)}{' '}
                          <span className="muted">
                            {reading.unit || SENSOR_UNITS[reading.sensor_type] || ''}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          );
        })}
      </div>

      {anomalies.data?.anomalies?.length > 0 && (
        <section className="card">
          <div className="card-header">
            <h2>Recent anomalies</h2>
            <span className="muted small">{anomalies.data.method.replace(/_/g, ' ')}</span>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Sensor</th>
                  <th className="num">Value</th>
                  <th>Severity</th>
                </tr>
              </thead>
              <tbody>
                {anomalies.data.anomalies.slice(0, 15).map((event, index) => (
                  <tr key={`${event.machine_id}-${event.recorded_at}-${index}`}>
                    <td>{formatTime(event.recorded_at)}</td>
                    <td className="primary">{event.sensor_type.replace(/_/g, ' ')}</td>
                    <td className="num">{formatNumber(event.value, 2)}</td>
                    <td>
                      <Pill tone={statusTone(event.severity)}>{event.severity}</Pill>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
