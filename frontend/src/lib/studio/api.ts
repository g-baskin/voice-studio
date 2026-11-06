// Studio calls keep the legacy page's own error wording, so they don't use the shared request().

type Detail = { loc?: (string | number)[]; msg?: string };

async function body(r: Response): Promise<unknown> {
  try {
    return await r.json();
  } catch {
    return null;
  }
}

function detailOf(j: unknown): unknown {
  return j && typeof j === 'object' && 'detail' in j ? j.detail : undefined;
}

/** Fetches /api/studio + path, turning errors into the messages the page shows. */
export async function api(path: string, opts: RequestInit = {}): Promise<Response> {
  const r = await fetch('/api/studio' + path, opts);
  if (!r.ok) {
    let msg = `Request failed (${r.status}).`;
    const d = detailOf(await body(r));
    if (typeof d === 'string') msg = d;
    else if (Array.isArray(d))
      msg = (d as Detail[]).map((x) => (x.loc ?? []).slice(1).join(' › ') + ': ' + (x.msg ?? '')).join('; ');
    if (r.status === 429) msg = 'Busy with another render or cleanup. Wait for it to finish, then try again.';
    throw new Error(msg);
  }
  return r;
}

export async function getJson<T>(path: string): Promise<T> {
  return (await (await api(path)).json()) as T;
}

export async function sendJson<T>(path: string, data: unknown, method = 'POST'): Promise<T> {
  const r = await api(path, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
  return (await r.json()) as T;
}

/** A string `detail` from an error body, or ''. */
export async function detailText(r: Response): Promise<string> {
  const d = detailOf(await body(r));
  return typeof d === 'string' ? d : '';
}

/** The script writer also reports validation lists by message only. */
export async function genDetail(r: Response): Promise<string> {
  const d = detailOf(await body(r));
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) return (d as Detail[]).map((x) => x.msg).join('; ');
  return '';
}

export async function llmError(r: Response): Promise<string> {
  return (await detailText(r)) || `The AI service answered with an error (${r.status}).`;
}

export const errorText = (e: unknown): string => (e instanceof Error ? e.message : String(e));

/** fetch() rejects with this when the app has stopped. */
export const reachText = (e: unknown): string =>
  errorText(e) === 'Failed to fetch' ? "Couldn't reach the app. Is it still running?" : errorText(e);

export const fileUrl = (job: string, name: string): string =>
  `/api/studio/render/${job}/file/${encodeURIComponent(name)}`;
