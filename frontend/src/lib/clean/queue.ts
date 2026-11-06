import type { Controls, PresetName } from './templates.ts';

export const MAX_FILES = 20;
export const MAX_BYTES = 500 * 1024 * 1024;
const MEDIA = /\.(wav|flac|mp3|m4a|aac|ogg|opus|aiff?|mp4|mov|mkv|webm|avi|m4v)$/i;

export type Mode = 'clean' | 'preview' | 'analyze';
export type Metrics = Record<string, number | null | undefined>;
export type JobResult = {
  mode: Mode;
  seconds: number;
  start: number;
  matching: { note: string };
  warnings: string[];
  before: Metrics;
  after: Metrics;
  suggestion?: { template: string; reason: string };
};
export type QueueItem = {
  file: File;
  status: 'queued' | 'processing' | 'done' | 'error';
  job: string | null;
  result: JobResult | null;
  error?: string | null;
  label?: string;
};
export type Snapshot = { preset: PresetName; controls: Controls; label: string };
export type Bounds = { start: number; seconds: number };
export type JobState = { status: string; progress?: number; step?: string; error?: string; result: JobResult };

/** Splits picked files into queue entries and rejection messages, honouring the 20-file limit. */
export function acceptFiles(queued: number, files: Iterable<File>): { accepted: QueueItem[]; rejected: string[] } {
  const accepted: QueueItem[] = [];
  const rejected: string[] = [];
  for (const f of files) {
    if (queued + accepted.length >= MAX_FILES) {
      rejected.push('Queue limit: 20 files.');
      break;
    }
    if (!MEDIA.test(f.name)) {
      rejected.push(f.name + ': unsupported type.');
      continue;
    }
    if (!f.size || f.size > MAX_BYTES) {
      rejected.push(f.name + ': empty or larger than 500 MB.');
      continue;
    }
    accepted.push({ file: f, status: 'queued', job: null, result: null });
  }
  return { accepted, rejected };
}

export function queueLine(item: QueueItem): string {
  return `${item.file.name}: ${item.status}${item.error ? ' (' + item.error + ')' : ''}`;
}

export type ActionInput = {
  templatesReady: boolean;
  hasFile: boolean;
  busy: boolean;
  queue: readonly QueueItem[];
  savedSelected: boolean;
  downloading: boolean;
};

/** Which controls are disabled; nothing can upload before the template settings load. */
export function actions(s: ActionInput) {
  const settingsLocked = s.busy || !s.templatesReady;
  return {
    run: !s.templatesReady || !s.hasFile || s.busy,
    batch: settingsLocked || !s.queue.some((item) => item.status !== 'done'),
    download: s.busy || s.downloading || !s.queue.some((item) => item.job),
    queue: s.busy,
    settings: settingsLocked,
    remove: s.busy || !s.savedSelected,
  };
}

export function section(start: number, seconds: number): Bounds {
  if (
    !Number.isFinite(start) ||
    start < 0 ||
    start > 86400 ||
    !Number.isFinite(seconds) ||
    seconds < 10 ||
    seconds > 20
  )
    throw new Error('Choose a start from 0 to 86400 seconds and a length from 10 to 20 seconds.');
  return { start, seconds };
}

export function cleanForm(file: File, mode: Mode, settings: Snapshot, bounds: Bounds): FormData {
  const fd = new FormData();
  fd.append('file', file);
  fd.append('mode', mode);
  fd.append('preset', settings.preset);
  for (const [k, v] of Object.entries(settings.controls)) fd.append(k, String(v));
  fd.append('start', String(bounds.start));
  fd.append('seconds', String(bounds.seconds));
  return fd;
}

/** Parses a JSON reply, turning error replies and unreadable bodies into readable errors. */
export async function responseJSON<T>(response: Response): Promise<T> {
  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new Error('The server returned an unreadable response.');
  }
  if (!response.ok) {
    const detail = data && typeof data === 'object' && 'detail' in data ? data.detail : undefined;
    throw new Error(typeof detail === 'string' ? detail : `Request failed (${response.status}).`);
  }
  return data as T;
}

export type JobHooks = {
  fetch: typeof fetch;
  status: (text: string) => void;
  progress: (fraction: number) => void;
  wait?: (ms: number) => Promise<void>;
};

export async function runJob(
  item: QueueItem,
  mode: Mode,
  settings: Snapshot,
  bounds: Bounds,
  hooks: JobHooks,
): Promise<{ job: string; result: JobResult }> {
  const wait = hooks.wait ?? ((ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms)));
  hooks.status(`Uploading ${item.file.name}…`);
  const body = cleanForm(item.file, mode, settings, bounds);
  const { job } = await responseJSON<{ job: string }>(await hooks.fetch('/api/clean', { method: 'POST', body }));
  // Poll sequentially so slow replies cannot overwrite newer state.
  for (;;) {
    const state = await responseJSON<JobState>(await hooks.fetch(`/api/jobs/${job}`));
    hooks.progress(state.progress || 0);
    if (state.status === 'error') throw new Error(state.error || 'Processing failed.');
    if (state.status === 'done') return { job, result: state.result };
    hooks.status(`${item.file.name}: ${state.step || 'Processing'}…`);
    await wait(700);
  }
}

export function batchSummary(completed: number, failed: number, stopped: boolean): string {
  return `${completed} completed, ${failed} failed.${stopped ? ' Stopped; remaining files stay queued.' : ''} Failed files can be retried with Process queue.`;
}

export function suggestionText(result: JobResult, label: string): string {
  return `Suggestion: ${label}. ${result.suggestion?.reason} Low confidence; based on ${result.seconds}s starting at ${result.start}s. Preview before committing.`;
}

export function clock(value: number): string {
  return `${Math.floor(value / 60)}:${String(Math.floor(value % 60)).padStart(2, '0')}`;
}

export type MetricRow = { label: string; before: string; after: string; tone: '' | 'good' | 'worse' };

const ROWS = [
  ['Listener prediction (1–5)', 'listener', '', 'up'],
  ['Voice-quality prediction (1–5)', 'voice', '', 'up'],
  ['Pause level (not an echo measurement)', 'echo_db', 'dB', null],
  ['Detected ringing', 'metallic', 'dB', 'down'],
  ['Brightness / harshness balance', 'harshness_db', 'dB', null],
] as const;

export function metricRows(b: Metrics, a: Metrics): MetricRow[] {
  return ROWS.map(([label, key, unit, direction]) => {
    const before = b[key],
      after = a[key];
    let tone: MetricRow['tone'] = '';
    if (direction && before != null && after != null) {
      const delta = (after - before) * (direction === 'up' ? 1 : -1);
      tone = delta > 0.1 ? 'good' : delta < -0.1 ? 'worse' : '';
    }
    return {
      label,
      before: before == null ? 'Unavailable' : `${before} ${unit}`,
      after: after == null ? 'Unavailable' : `${after} ${unit}`,
      tone,
    };
  });
}

export function resultTitle(name: string, result: JobResult): string {
  return `${name}: ${result.mode === 'preview' ? 'preview' : 'full-file result'}`;
}

export function resultSettings(label: string, result: JobResult): string {
  return `${label}. ${result.seconds}s${result.mode === 'preview' ? ' starting at ' + result.start + 's' : ''}.`;
}

export function scopeNote(after: Metrics): string {
  return `DNSMOS predictions use up to the first 60 seconds (${after.score_seconds ?? after.seconds}s scored here). Higher predicted ratings are preferred; less detected ringing may help. Other measures describe changes, not quality verdicts.`;
}
