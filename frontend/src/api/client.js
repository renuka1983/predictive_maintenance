/**
 * Thin API client.
 *
 * Every request carries the X-Tenant-ID header, which is how the backend
 * scopes data. A 403 from a maturity-gated endpoint is turned into a typed
 * FeatureLockedError so the UI can render an upgrade prompt rather than an
 * error banner.
 */

const BASE_URL = import.meta.env.VITE_API_BASE_URL || '';
const API_PREFIX = `${BASE_URL}/api/v1`;

export class ApiError extends Error {
  constructor(message, status, body) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
  }
}

export class FeatureLockedError extends ApiError {
  constructor(detail) {
    super(detail.message || 'Feature not available', 403, detail);
    this.name = 'FeatureLockedError';
    this.featureKey = detail.feature_key;
    this.requiredLevel = detail.required_level;
    this.currentLevel = detail.current_level;
  }
}

async function request(path, { tenantId, method = 'GET', body, signal } = {}) {
  const headers = { Accept: 'application/json' };
  if (tenantId) headers['X-Tenant-ID'] = tenantId;
  if (body !== undefined) headers['Content-Type'] = 'application/json';

  const response = await fetch(`${API_PREFIX}${path}`, {
    method,
    headers,
    signal,
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  let payload = null;
  const text = await response.text();
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = text;
    }
  }

  if (!response.ok) {
    const detail = payload?.detail;
    // The feature gate returns a structured detail object; a plain string
    // detail is an ordinary error.
    if (response.status === 403 && detail && typeof detail === 'object') {
      throw new FeatureLockedError(detail);
    }
    const message =
      typeof detail === 'string' ? detail : `Request failed (${response.status})`;
    throw new ApiError(message, response.status, payload);
  }

  return payload;
}

const qs = (params) => {
  const search = new URLSearchParams();
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      search.append(key, value);
    }
  });
  const string = search.toString();
  return string ? `?${string}` : '';
};

export const api = {
  health: () => request('/../../health'),

  // --- tenants (no tenant header required) ---------------------------
  listTenants: () => request('/tenants?limit=100'),
  getTenant: (id) => request(`/tenants/${id}`),
  getMaturity: (id, refresh = false) =>
    request(`/tenants/${id}/maturity${qs({ refresh })}`),
  assess: (id) => request(`/tenants/${id}/assess`, { method: 'POST' }),
  listFeatures: (id) => request(`/tenants/${id}/features`),
  setFeature: (id, key, enabled) =>
    request(`/tenants/${id}/features/${key}`, { method: 'PUT', body: { enabled } }),
  listLevels: () => request('/tenants/levels'),

  // --- tenant-scoped resources ---------------------------------------
  dashboard: (tenantId) => request('/analytics/dashboard', { tenantId }),

  listMachines: (tenantId, params) =>
    request(`/machines${qs(params)}`, { tenantId }),
  machineStatuses: (tenantId) => request('/machines/status', { tenantId }),
  listLines: (tenantId) => request('/machines/lines', { tenantId }),

  maintenanceStats: (tenantId, windowDays = 365) =>
    request(`/maintenance/stats${qs({ window_days: windowDays })}`, { tenantId }),
  listMaintenance: (tenantId, params) =>
    request(`/maintenance${qs(params)}`, { tenantId }),

  lineView: (tenantId, line, windowDays = 30) =>
    request(`/production/lines/${encodeURIComponent(line)}${qs({ window_days: windowDays })}`, {
      tenantId,
    }),

  weibull: (tenantId, machineId) =>
    request(`/analytics/reliability/weibull${qs({ machine_id: machineId })}`, { tenantId }),
  risk: (tenantId, params) => request(`/analytics/risk${qs(params)}`, { tenantId }),
  cascade: (tenantId, machineId, downtimeHours) =>
    request(`/analytics/cascade/${machineId}${qs({ downtime_hours: downtimeHours })}`, {
      tenantId,
    }),
  simulate: (tenantId, machineId, downtimeHours) =>
    request(
      `/analytics/simulate${qs({ machine_id: machineId, downtime_hours: downtimeHours })}`,
      { tenantId, method: 'POST' },
    ),
  roi: (tenantId) => request('/analytics/roi', { tenantId }),
  anomalies: (tenantId, windowHours = 24) =>
    request(`/analytics/anomalies${qs({ window_hours: windowHours })}`, { tenantId }),
  rul: (tenantId) => request('/analytics/rul', { tenantId }),
  benchmark: (tenantId) => request('/analytics/benchmark', { tenantId }),

  latestReadings: (tenantId) => request('/sensors/latest', { tenantId }),
  sensorSeries: (tenantId, machineId, sensorType, windowHours = 24) =>
    request(
      `/sensors/series${qs({
        machine_id: machineId,
        sensor_type: sensorType,
        window_hours: windowHours,
      })}`,
      { tenantId },
    ),
};
