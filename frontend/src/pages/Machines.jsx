import { api } from '../api/client';
import { ErrorState, Loading, Meter, Pill } from '../components/States';
import { useApi } from '../hooks/useApi';
import { useTenant } from '../hooks/useTenant';
import {
  formatCurrency,
  formatHours,
  formatNumber,
  machineTone,
} from '../utils/formatters';

/** Health below 50 is the point at which a machine warrants attention. */
const healthTone = (score) =>
  score >= 75 ? 'good' : score >= 50 ? 'warning' : score >= 25 ? 'serious' : 'critical';

export default function Machines() {
  const { tenantId } = useTenant();
  const { data, error, loading, reload } = useApi(
    () => api.machineStatuses(tenantId),
    [tenantId],
    { enabled: Boolean(tenantId) },
  );

  if (loading) return <Loading label="Loading machines…" />;
  if (error) return <ErrorState error={error} onRetry={reload} />;

  const machines = data || [];

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h1>Machines</h1>
          <p>
            {machines.length} assets, worst health first. Health combines failure
            count, downtime and current status, weighted by criticality.
          </p>
        </div>
      </div>

      <section className="card">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Code</th>
                <th>Name</th>
                <th>Status</th>
                <th className="num">Criticality</th>
                <th className="num">Failures</th>
                <th className="num">Downtime</th>
                <th className="num">MTBF</th>
                <th className="num">Cost</th>
                <th className="num">Health</th>
              </tr>
            </thead>
            <tbody>
              {machines.map((machine) => (
                <tr key={machine.machine_id}>
                  <td className="primary">{machine.machine_code}</td>
                  <td>{machine.name}</td>
                  <td>
                    <Pill tone={machineTone(machine.status)}>{machine.status}</Pill>
                  </td>
                  <td className="num">{machine.criticality}</td>
                  <td className="num">{machine.failure_count}</td>
                  <td className="num">{formatHours(machine.total_downtime_hours)}</td>
                  <td className="num">{formatHours(machine.mtbf_hours)}</td>
                  <td className="num">
                    {formatCurrency(machine.total_maintenance_cost)}
                  </td>
                  <td className="num">
                    <Meter
                      value={machine.health_score / 100}
                      tone={healthTone(machine.health_score)}
                      label={formatNumber(machine.health_score)}
                    />
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
