// The page's only way to the pet: three calls to RoomAPI in room.py. Today they
// go over HTTP to the pet's 127.0.0.1 server; under Electron this file becomes
// three ipcRenderer.invoke calls and nothing else changes.
import type {Catalog, Comfort, Layout, State} from './model';

const token = new URLSearchParams(location.search).get('t') ?? '';

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: {'X-Room-Token': token, ...(body === undefined ? {} : {'Content-Type': 'application/json'})},
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({error: `HTTP ${res.status}`}));
  if (!res.ok) throw new Error(data.error ?? `HTTP ${res.status}`);
  return data as T;
}

export const api = {
  catalog: () => call<Catalog>('GET', '/api/catalog'),
  state: () => call<State>('GET', '/api/state'),
  putLayout: (layout: Layout) => call<{layout: Layout; comfort: Comfort}>('PUT', '/api/layout', layout),
};
