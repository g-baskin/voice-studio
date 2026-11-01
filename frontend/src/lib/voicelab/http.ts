export const API = '/api/voicelab';

/** Voice Lab wording for a failed response, matching the server's detail when it has one. */
async function errorText(res: Response): Promise<string> {
  if (res.status === 429)
    return 'Another voice job is running on this computer. Wait for it to finish, then try again.';
  try {
    const j: unknown = await res.json();
    if (j && typeof j === 'object' && 'detail' in j) {
      const detail: unknown = j.detail;
      if (typeof detail === 'string') return detail;
      if (Array.isArray(detail) && detail[0]) {
        const first: unknown = detail[0];
        const msg = first && typeof first === 'object' && 'msg' in first && first.msg ? String(first.msg) : '';
        return 'Check the inputs: ' + (msg || 'invalid value') + '.';
      }
    }
  } catch {
    // Not JSON.
  }
  return 'Something went wrong (' + res.status + '). Try again.';
}

export async function call(url: string, init?: RequestInit): Promise<Response> {
  let res: Response;
  try {
    res = await fetch(url, init);
  } catch (cause) {
    throw new Error('Could not reach Shark Audio. Is the app still running?', { cause });
  }
  if (!res.ok) throw new Error(await errorText(res));
  return res;
}

export async function json<T>(url: string, body: unknown, method = 'POST'): Promise<T> {
  const res = await call(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  return (await res.json()) as T;
}

/** Cloning-panel requests keep that panel's own error wording. */
export async function cloneApi(url: string, init?: RequestInit): Promise<Response> {
  const r = await fetch(url, init);
  if (!r.ok) {
    let msg: unknown = `Request failed (${r.status}).`;
    try {
      const body: unknown = await r.json();
      if (body && typeof body === 'object' && 'detail' in body && body.detail) msg = body.detail;
    } catch {
      // Not JSON.
    }
    throw new Error(typeof msg === 'string' ? msg : 'Invalid input.');
  }
  return r;
}

export const errorMessage = (e: unknown): string => (e instanceof Error ? e.message : String(e));
