import { createContext, createElement, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { api } from '../api/client';

const TenantContext = createContext(null);
const STORAGE_KEY = 'mfg-ai.tenant';

/**
 * Holds the selected tenant and its feature set.
 *
 * Feature keys are loaded once per tenant and shared through context, so
 * navigation can hide locked pages without every component refetching.
 */
export function TenantProvider({ children }) {
  const [tenants, setTenants] = useState([]);
  const [tenantId, setTenantIdState] = useState(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) || import.meta.env.VITE_DEFAULT_TENANT || '';
    } catch {
      return import.meta.env.VITE_DEFAULT_TENANT || '';
    }
  });
  const [features, setFeatures] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const setTenantId = useCallback((next) => {
    setTenantIdState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* storage unavailable (private mode) - selection is session-only */
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    api
      .listTenants()
      .then((page) => {
        if (cancelled) return;
        setTenants(page.items);
        // Fall back to the first tenant if the stored one no longer exists.
        if (page.items.length && !page.items.some((t) => t.slug === tenantId || t.id === tenantId)) {
          setTenantId(page.items[0].slug);
        }
      })
      .catch((caught) => !cancelled && setError(caught))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const refreshFeatures = useCallback(() => {
    if (!tenantId) return Promise.resolve();
    return api
      .listFeatures(tenantId)
      .then(setFeatures)
      .catch(() => setFeatures(null));
  }, [tenantId]);

  useEffect(() => {
    refreshFeatures();
  }, [refreshFeatures]);

  const tenant = useMemo(
    () => tenants.find((t) => t.slug === tenantId || t.id === tenantId) || null,
    [tenants, tenantId],
  );

  const enabledKeys = useMemo(
    () => new Set((features?.enabled || []).map((f) => f.feature_key)),
    [features],
  );

  const value = useMemo(
    () => ({
      tenants,
      tenant,
      tenantId,
      setTenantId,
      features,
      enabledKeys,
      hasFeature: (key) => enabledKeys.has(key),
      level: features?.maturity_level ?? tenant?.maturity_level ?? 0,
      loading,
      error,
      refreshFeatures,
    }),
    [tenants, tenant, tenantId, setTenantId, features, enabledKeys, loading, error, refreshFeatures],
  );

  return createElement(TenantContext.Provider, { value }, children);
}

export function useTenant() {
  const context = useContext(TenantContext);
  if (!context) throw new Error('useTenant must be used inside a TenantProvider');
  return context;
}
