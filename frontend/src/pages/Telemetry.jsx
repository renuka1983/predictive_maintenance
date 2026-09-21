import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { TrendLine } from '../components/Charts';
import { ErrorState, Loading } from '../components/States';
import { useApi } from '../hooks/useApi';
import { useTenant } from '../hooks/useTenant';
import { formatNumber, formatTime } from '../utils/formatters';

const SENSOR_TYPES = ['vibration', 'temperature', 'pressure', 'current', 'rpm'];
const WINDOWS = [
  { label: 'Last 6 hours', value: 6 },
  { label: 'Last 24 hours', value: 24 },
  { label: 'Last 7 days', value: 168 },
];

export default function Telemetry() {
  const { tenantId } = useTenant();
  const [machineId, setMachineId] = useState('');
  const [sensorType, setSensorType] = useState('vibration');
  const [windowHours, setWindowHours] = useState(24);

  const machines = useApi(
    () => api.listMachines(tenantId, { has_sensors: true, limit: 200 }),
    [tenantId],
    { enabled: Boolean(tenantId) },
  );

  useEffect(() => {
    const first = machines.data?.items?.[0];
    if (!machineId && first) setMachineId(first.id);
  }, [machines.data, machineId]);

  const series = useApi(
    () => api.sensorSeries(tenantId, machineId, sensorType, windowHours),
    [tenantId, machineId, sensorType, windowHours],
    { enabled: Boolean(tenantId && machineId) },
  );

  if (machines.loading) return <Loading label="Loading instrumented machines…" />;
  if (machines.error) return <ErrorState error={machines.error} onRetry={machines.reload} />;
  if (!machines.data?.items?.length) {
    return <div className="state">No machines are flagged as instrumented yet.</div>;
  }

  const data = series.data;

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h1>Sensor telemetry</h1>
          <p>Raw IoT measurements, downsampled for display.</p>
        </div>
      </div>

      <div className="control-row">
        <div className="field">
          <label htmlFor="t-machine">Machine</label>
          <select
            id="t-machine"
            value={machineId}
            onChange={(event) => setMachineId(event.target.value)}
          >
            {machines.data.items.map((machine) => (
              <option key={machine.id} value={machine.id}>
                {machine.machine_code}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="t-sensor">Sensor</label>
          <select
            id="t-sensor"
            value={sensorType}
            onChange={(event) => setSensorType(event.target.value)}
          >
            {SENSOR_TYPES.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="t-window">Window</label>
          <select
            id="t-window"
            value={windowHours}
            onChange={(event) => setWindowHours(Number(event.target.value))}
          >
            {WINDOWS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {series.loading && <Loading />}
      {series.error && <ErrorState error={series.error} onRetry={series.reload} />}

      {data && (
        <>
          <div className="grid cols-3">
            <div className="stat">
              <span className="stat-label">Mean</span>
              <span className="stat-value">{formatNumber(data.mean, 2)}</span>
              <span className="stat-sub">{data.unit || ''}</span>
            </div>
            <div className="stat">
              <span className="stat-label">Minimum</span>
              <span className="stat-value">{formatNumber(data.minimum, 2)}</span>
              <span className="stat-sub">{data.unit || ''}</span>
            </div>
            <div className="stat">
              <span className="stat-label">Maximum</span>
              <span className="stat-value">{formatNumber(data.maximum, 2)}</span>
              <span className="stat-sub">{data.unit || ''}</span>
            </div>
          </div>

          <section className="card">
            <div className="card-header">
              <h2>
                {sensorType.replace(/_/g, ' ')}
                {data.unit ? ` (${data.unit})` : ''}
              </h2>
              <span className="muted small">{data.points.length} points</span>
            </div>
            {data.points.length === 0 ? (
              <div className="state">No readings in this window.</div>
            ) : (
              <TrendLine
                data={data.points}
                xKey="recorded_at"
                valueKey="value"
                label={sensorType}
                height={280}
                labelFormatter={formatTime}
                valueFormatter={(value) => `${formatNumber(value, 3)} ${data.unit || ''}`}
              />
            )}
          </section>
        </>
      )}
    </div>
  );
}
