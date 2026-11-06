import type {
  Analysis,
  AnalysisKind,
  CaptionFont,
  ExportJob,
  FillerCandidate,
  HookCandidate,
  Media,
  Sequence,
  SequenceSummary,
  TranscribeStatus,
  Transcript,
  TranscriptJob,
  Word,
} from './types.ts';

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

/** One part of a batch export: a sequence range written as its own file. */
export type ExportRange = { in: number; out: number; label: string };

export const startExport = (sequence: Sequence, inOut: boolean, quality: string, ranges: ExportRange[] | null = null) =>
  json<ExportJob>('/exports', send('POST', { sequence, in_out: inOut, quality, ranges }));
export const exportStatus = (id: string) => json<ExportJob>(`/exports/${id}`);
export const cancelExport = (id: string) => json<ExportJob>(`/exports/${id}/cancel`, { method: 'POST' });
export const exportFileUrl = (id: string, index = 0) => `/api/editor/exports/${id}/file?index=${index}`;

/** Settings for one analysis; the server clamps and validates each. */
export type AnalysisParams = {
  noise_db?: number;
  min_seconds?: number;
  threshold?: number;
  min_length?: number;
  max_length?: number;
  count?: number;
};

export const startAnalysis = (media: string, kind: AnalysisKind, params: AnalysisParams = {}) =>
  json<Analysis>(`/media/${media}/analysis`, send('POST', { kind, ...params }));
export const analysisStatus = (media: string, id: string) => json<Analysis>(`/media/${media}/analysis/${id}`);
export const cancelAnalysis = (media: string, id: string) =>
  json<Analysis>(`/media/${media}/analysis/${id}/cancel`, { method: 'POST' });

export const transcribeStatus = () => json<TranscribeStatus>('/transcribe/status');
export const startTranscript = (media: string, overwrite = false) =>
  json<TranscriptJob>(`/media/${media}/transcript`, send('POST', { overwrite }));
export const transcriptJob = (media: string, id: string) => json<TranscriptJob>(`/media/${media}/transcript/job/${id}`);
export const cancelTranscript = (media: string, id: string) =>
  json<TranscriptJob>(`/media/${media}/transcript/job/${id}/cancel`, { method: 'POST' });

/** A saved transcript plus filler picks; `silence` names the silence analysis still needed for gap picks. */
export type TranscriptReply = Transcript & {
  fillers: FillerCandidate[];
  silence: { noise_db: number; min_seconds: number } | null;
};

/** The media's transcript, or null when it has none yet. */
/** The media's transcript, or null before it has been transcribed. */
export const getTranscript = (media: string, extra = false) =>
  json<TranscriptReply | null>(`/media/${media}/transcript?extra=${extra}`);
export const saveTranscript = (media: string, words: Word[]) =>
  json<Transcript>(`/media/${media}/transcript`, send('PUT', { words }));

export type HookParams = { min_len: number; max_len: number; count: number; use_ai: boolean };
export const findHooks = (media: string, params: HookParams) =>
  json<{ hooks: HookCandidate[]; ranked_by: 'structure' | 'ai' }>(`/media/${media}/hooks`, send('POST', params));

export const captionFontUrl = (key: CaptionFont) => `/api/editor/caption-fonts/${key}`;

/** Download the sequence's captions as a SubRip (.srt) file. */
export async function downloadSrt(seq: Sequence): Promise<void> {
  const blob = await (await call('/sequences/captions.srt', send('POST', seq))).blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${seq.name.replace(/[^A-Za-z0-9 _.-]+/g, '').trim() || 'sequence'}.srt`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
