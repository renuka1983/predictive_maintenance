async function req<T>(method: string, url: string, body?: unknown): Promise<T> {
  const r = await fetch(url, {
    method,
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`;
    try { msg = (await r.json()).detail ?? msg; } catch { /* ignore */ }
    throw new Error(msg);
  }
  return r.json() as Promise<T>;
}
export const api = {
  get: <T = any>(url: string) => req<T>('GET', url),
  post: <T = any>(url: string, body: unknown = {}) => req<T>('POST', url, body),
  del: <T = any>(url: string) => req<T>('DELETE', url),
};
