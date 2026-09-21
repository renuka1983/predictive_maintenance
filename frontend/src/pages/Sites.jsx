import { useState } from 'react';
import { api } from '../api/client';
import { ErrorState, Loading, Pill } from '../components/States';
import { useApi } from '../hooks/useApi';
import { useTenant } from '../hooks/useTenant';
import { formatNumber } from '../utils/formatters';

/**
 * Level 4 site registry.
 *
 * Machines already carry a site name; this page attaches region and country
 * to those names so rollups can group by region. Sites used by machines but
 * absent here still appear in rollups — they just cannot be grouped.
 */
export default function Sites() {
  const { tenantId } = useTenant();
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(null);
  const [draft, setDraft] = useState({ region: '', country: '' });

  const sites = useApi(() => api.listSites(tenantId), [tenantId], {
    enabled: Boolean(tenantId),
  });
  const sync = async () => {
    setBusy(true);
    try {
      await api.syncSites(tenantId);
      await sites.reload();
    } finally {
      setBusy(false);
    }
  };

  const startEdit = (site) => {
    setEditing(site.name);
    setDraft({ region: site.region || '', country: site.country || '' });
  };

  const save = async (site) => {
    setBusy(true);
    try {
      await api.updateSite(tenantId, site.name, {
        region: draft.region || null,
        country: draft.country || null,
      });
      setEditing(null);
      await sites.reload();
    } finally {
      setBusy(false);
    }
  };

  if (sites.loading) return <Loading label="Loading site registry…" />;
  if (sites.error) return <ErrorState error={sites.error} onRetry={sites.reload} />;

  const rows = sites.data || [];
  const unassigned = rows.filter((site) => !site.region).length;

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h1>Site registry</h1>
          <p>
            {rows.length} registered plants
            {unassigned > 0 && ` · ${unassigned} without a region`}
          </p>
        </div>
        <button type="button" onClick={sync} disabled={busy}>
          {busy ? 'Working…' : 'Sync from machines'}
        </button>
      </div>

      <section className="card">
        <p className="card-note">
          A site's <strong>name</strong> must match the <code>site</code> value on
          its machines — that string is the join key. Adding a region lets the
          portfolio roll up by region.
        </p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Site</th>
                <th>Region</th>
                <th>Country</th>
                <th className="num">Machines</th>
                <th>Status</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((site) => (
                <tr key={site.id}>
                  <td className="primary">{site.display_name || site.name}</td>
                  <td>
                    {editing === site.name ? (
                      <input
                        type="text"
                        value={draft.region}
                        placeholder="e.g. Europe"
                        onChange={(event) =>
                          setDraft((d) => ({ ...d, region: event.target.value }))
                        }
                      />
                    ) : (
                      site.region || <span className="muted">—</span>
                    )}
                  </td>
                  <td>
                    {editing === site.name ? (
                      <input
                        type="text"
                        value={draft.country}
                        placeholder="e.g. Czechia"
                        onChange={(event) =>
                          setDraft((d) => ({ ...d, country: event.target.value }))
                        }
                      />
                    ) : (
                      site.country || <span className="muted">—</span>
                    )}
                  </td>
                  <td className="num">{formatNumber(site.machine_count)}</td>
                  <td>
                    {site.machine_count === 0 ? (
                      <Pill tone="warning">no machines</Pill>
                    ) : site.region ? (
                      <Pill tone="good">grouped</Pill>
                    ) : (
                      <Pill tone="neutral">ungrouped</Pill>
                    )}
                  </td>
                  <td>
                    {editing === site.name ? (
                      <div className="inline-list">
                        <button
                          type="button"
                          className="primary"
                          disabled={busy}
                          onClick={() => save(site)}
                        >
                          Save
                        </button>
                        <button type="button" onClick={() => setEditing(null)}>
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <button type="button" onClick={() => startEdit(site)}>
                        Edit
                      </button>
                    )}
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
