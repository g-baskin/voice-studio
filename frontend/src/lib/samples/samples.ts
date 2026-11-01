export type Person = { id: string; name: string; active?: string };
export type Turn = { start: number; end: number; speaker: number; overlap: boolean };
export type SourceSummary = { id: string; name: string };
export type Source = {
  id: string;
  name: string;
  status: 'running' | 'done' | 'error' | string;
  step: string;
  error?: string;
  duration?: number;
  segments?: Turn[];
  separate: boolean;
  start: number;
};
export type Sample = {
  id: string;
  seconds: number;
  source_name: string;
  start: number;
  end: number;
  clipped: boolean;
  rms_db: number;
  cleaned: boolean;
};
export type Version = { id: string; name: string; meta: { reference_version: number; seconds: number } };
export type Library = { people: Person[]; sources: SourceSummary[]; installed: boolean; setup: string };
export type PersonDetail = { id: string; name: string; active?: string; samples: Sample[]; versions: Version[] };
export type PreviewJob = { job: string };
export type PreviewResult = { status: 'running' | 'done' | 'error' | string; error?: string };

export const POLL_MS = 2000;
export const MIN_SECONDS = 5;
export const MAX_SECONDS = 20;

function detail(data: unknown): string {
  return data && typeof data === 'object' && 'detail' in data && typeof data.detail === 'string'
    ? data.detail
    : 'Check the form values and retry.';
}

/** Fetches a same-origin JSON API path; errors carry the server's detail message. */
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  const data: unknown = await response.json();
  if (!response.ok) throw new Error(detail(data));
  return data as T;
}

export function post<T>(path: string, body: object): Promise<T> {
  return api<T>(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
}

/** Keeps a previous selection only if it is still offered. */
export function keep(previous: string, rows: { id: string }[]): string {
  return rows.some((row) => row.id === previous) ? previous : '';
}

export function turnLabel(turn: Turn): string {
  return `Speaker ${turn.speaker + 1}: ${turn.start.toFixed(1)} to ${turn.end.toFixed(1)} s${turn.overlap ? ' (overlap)' : ''}`;
}

export function sourceSummary(source: Source): string {
  return `${source.segments?.length ?? 0} speaker turns. Source offset: ${source.start} seconds. ${source.separate ? 'Background separation applied.' : 'No background separation: both players contain the original window.'}`;
}

export function sampleLabel(sample: Sample): string {
  return `${sample.seconds.toFixed(2)} s from ${sample.source_name} (${sample.start.toFixed(2)} to ${sample.end.toFixed(2)} s)`;
}

export function sampleInfo(sample: Sample): string {
  return `${sample.cleaned ? 'Dialogue' : 'Original'} audio. Level: ${sample.rms_db} dB RMS.${sample.clipped ? ' Possible clipping: consider another sample.' : ''}`;
}

export function collectionSummary(person: PersonDetail): string {
  const count = person.samples.length;
  return `${person.name}: ${count} approved samples. ${count ? 'Check the samples for your next reference.' : 'Save a reviewed selection above to start.'}`;
}
