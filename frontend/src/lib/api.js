// AutoBOM frontend API helper.
//
// Created in Phase 0 but NOT yet consumed — the prototype still runs entirely on
// its in-memory seed store (core/store.jsx). Phase 3 replaces the store's mock
// action bodies with calls through this helper, screen by screen, preserving the
// UI contract.
//
// All requests go to /api (same-origin in dev via the Vite proxy → FastAPI on
// :8000; same-origin in production behind the deployed gateway).

const BASE = '/api';

async function request(path, { method = 'GET', body, headers } = {}) {
  const res = await fetch(`${BASE}${path}`, {
    method,
    credentials: 'include',
    headers: {
      ...(body ? { 'Content-Type': 'application/json' } : {}),
      ...(headers || {}),
    },
    body: body != null ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const err = new Error((data && data.detail) || `HTTP ${res.status}`);
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}

export const api = {
  get: (path, opts) => request(path, { ...opts, method: 'GET' }),
  post: (path, body, opts) => request(path, { ...opts, method: 'POST', body }),
  patch: (path, body, opts) => request(path, { ...opts, method: 'PATCH', body }),
  del: (path, opts) => request(path, { ...opts, method: 'DELETE' }),
  health: () => request('/health'),
};

export default api;
