import type { ExportJob, Media, Sequence, SequenceSummary } from './types.ts';

type Detail = { loc?: (string | number)[]; msg?: string };

/** Fetches an /api/editor path; validation and server errors become readable messages. */
export async function call(path: string, init: RequestInit = {}): Promise<Response> {
  const response = await fetch('/api/editor' + path, init);
  if (response.ok) return response;
  let message = `Request failed (${response.status}).`;
  try {
    const body: unknown = await response.json();
    const detail = body && typeof body === 'object' && 'detail' in body ? body.detail : undefined;
    if (typeof detail === 'string') message = detail;
    else if (Array.isArray(detail))
      message = (detail as Detail[]).map((d) => (d.msg ?? '').replace(/^Value error, /, '')).join(' ');
  } catch {
    // A non-JSON error keeps the status message.
  }
  if (response.status === 429) message = 'Busy with another export or file. Wait for it to finish, then retry.';
  throw new Error(message);
}

async function json<T>(path: string, init: RequestInit = {}): Promise<T> {
  return (await (await call(path, init)).json()) as T;
}

function send(method: string, data: unknown): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) };
}

export const listMedia = () => json<Media[]>('/media');
export const getMedia = (id: string) => json<Media>(`/media/${id}`);
export const removeMedia = (id: string) => call(`/media/${id}`, { method: 'DELETE' });
export const proxyUrl = (id: string) => `/api/editor/media/${id}/proxy`;
export const thumbsUrl = (id: string) => `/api/editor/media/${id}/thumbs`;
export const peaksUrl = (id: string) => `/api/editor/media/${id}/peaks`;

export function uploadMedia(file: File): Promise<Media> {
  return json<Media>(`/media?name=${encodeURIComponent(file.name)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/octet-stream' },
    body: file,
  });
}

export const listSequences = () => json<SequenceSummary[]>('/sequences');
export const getSequence = (id: string) => json<Sequence & SequenceSummary>(`/sequences/${id}`);
export const createSequence = (seq: Sequence) => json<Sequence & SequenceSummary>('/sequences', send('POST', seq));
export const saveSequence = (id: string, seq: Sequence) =>
  json<Sequence & SequenceSummary>(`/sequences/${id}`, send('PUT', seq));
export const deleteSequence = (id: string) => call(`/sequences/${id}`, { method: 'DELETE' });

export const startExport = (sequence: Sequence, inOut: boolean, quality: string) =>
  json<ExportJob>('/exports', send('POST', { sequence, in_out: inOut, quality }));
export const exportStatus = (id: string) => json<ExportJob>(`/exports/${id}`);
export const cancelExport = (id: string) => json<ExportJob>(`/exports/${id}/cancel`, { method: 'POST' });
export const exportFileUrl = (id: string) => `/api/editor/exports/${id}/file`;
