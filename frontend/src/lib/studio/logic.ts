import type { EditorProject, Line, ProjectInput, ProjectPayload, Style, Voice } from './types.ts';

export const DRAFT = 'nv-studio-draft-v1';
export const MAX_LINES = 500;
export const DEFAULT_TEXT = 'Welcome to Shark Audio Studio. [pause 0.5s] Write your script, then press Render.';

export const DELIVERY: Record<string, string> = {
  neutral: 'Neutral',
  warm: 'Warm',
  energetic: 'Energetic',
  calm: 'Calm',
  serious: 'Serious',
  excited: 'Excited',
  soft: 'Soft',
};

export const FALLBACK_VOICE: Voice = {
  id: 'af_heart',
  name: 'Heart',
  kind: 'stock',
  gender: 'female',
  language: 'American English',
};

export const uid = (): string =>
  Array.from(crypto.getRandomValues(new Uint8Array(6)), (b) => b.toString(16).padStart(2, '0')).join('');

export const newLine = (voice = 'af_heart', speaker = '', text = ''): Line => ({
  id: uid(),
  text,
  voice,
  speaker,
  speed: 1,
  pitch: 0,
  volume: 0,
  pause: 0.4,
  delivery: 'neutral',
  take: 0,
  takes: [0],
  target: null,
  start: null,
  end: null,
});

const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const numOr = (v: unknown, d: number): number => (isNum(v) ? v : d);
const numOrNull = (v: unknown): number | null => (isNum(v) ? v : null);
const strOr = (v: unknown, d: string): string => (typeof v === 'string' ? v : d);

/** Fills defaults for older, partial or damaged lines (drafts can come from a restored backup). */
export function normalLine(raw: unknown): Line {
  const l: Partial<Record<keyof Line, unknown>> = raw && typeof raw === 'object' ? raw : {};
  const base = newLine();
  const takes = Array.isArray(l.takes) ? l.takes.filter(isNum) : [];
  const line: Line = {
    id: strOr(l.id, base.id) || base.id,
    text: strOr(l.text, ''),
    voice: strOr(l.voice, base.voice) || base.voice,
    speaker: strOr(l.speaker, ''),
    speed: numOr(l.speed, base.speed),
    pitch: numOr(l.pitch, base.pitch),
    volume: numOr(l.volume, base.volume),
    pause: numOr(l.pause, base.pause),
    delivery: strOr(l.delivery, base.delivery) || base.delivery,
    take: numOr(l.take, 0),
    takes: takes.length ? takes : [0],
    target: numOrNull(l.target),
    start: numOrNull(l.start),
    end: numOrNull(l.end),
  };
  if (typeof l.note === 'string') line.note = l.note;
  if (l.style && typeof l.style === 'object') line.style = l.style as Style;
  if (!line.takes.includes(line.take)) line.take = line.takes[0];
  return line;
}

/** Keeps only string-to-string entries, for the dictionary and cast of a stored project. */
function stringMap(v: unknown): Record<string, string> {
  const out: Record<string, string> = {};
  if (v && typeof v === 'object' && !Array.isArray(v))
    for (const [k, val] of Object.entries(v)) if (typeof val === 'string') out[k] = val;
  return out;
}

export function toEditor(p: ProjectInput): EditorProject {
  const lines: unknown[] = Array.isArray(p.lines) ? p.lines.slice(0, MAX_LINES) : [];
  return {
    title: (typeof p.title === 'string' && p.title) || 'Untitled project',
    lines: lines.map(normalLine),
    dictionary: Object.entries(stringMap(p.dictionary)),
    cast: stringMap(p.cast),
    mode: p.mode === 'timed' ? 'timed' : 'sequential',
  };
}

export function toPayload(p: EditorProject): ProjectPayload {
  const dictionary: Record<string, string> = {};
  for (const [w, v] of p.dictionary) if (w.trim() && v.trim()) dictionary[w.trim()] = v.trim();
  return {
    title: p.title || 'Untitled project',
    lines: p.lines,
    dictionary,
    cast: p.cast,
    mode: p.mode || 'sequential',
  };
}

export const signed = (v: number): string => `${v >= 0 ? '+' : ''}${v}`;

export const voiceLabel = (v: Voice): string =>
  v.kind === 'stock' ? `${v.name} · ${v.gender}, ${v.language}` : v.name;

export type VoiceGroup = { label: string; voices: Voice[] };

/** Starred voices first (they also stay in their own group), then stock, Voice Lab and cloned voices. */
export function voiceGroups(catalog: Voice[]): VoiceGroup[] {
  const kindOf = (v: Voice) => (v.kind === 'clone' ? 'clone' : v.kind === 'stock' ? 'stock' : 'custom');
  const groups: VoiceGroup[] = [{ label: '\u2605 Starred', voices: catalog.filter((v) => v.starred) }];
  for (const [kind, label] of [
    ['stock', 'Stock voices'],
    ['custom', 'My voices (Voice Lab)'],
    ['clone', 'Cloned voices'],
  ])
    groups.push({ label, voices: catalog.filter((v) => kindOf(v) === kind) });
  return groups.filter((g) => g.voices.length);
}

export const styleDesc = (st: Style): string =>
  `${st.speed}× speed, ${signed(st.pitch)} st, ${signed(st.gain)} dB, pauses ×${st.pause}, ${st.pause_after} s after` +
  (st.eq.length ? `, EQ ${st.eq.map((b) => `${b[0]} ${b[1]} Hz ${signed(b[2])} dB`).join(', ')}` : '');

export function lineWarnings(text: string): string {
  const w: string[] = [];
  for (const m of text.matchAll(/\[([^\]\n[]{1,40})\]/g)) {
    const b = m[1].trim();
    const p = b.match(/^pause\s+(\d+(?:\.\d+)?)\s*(s|sec|ms)?$/i);
    if (p) {
      const s = Number(p[1]) / ((p[2] || '').toLowerCase() === 'ms' ? 1000 : 1);
      if (s < 0.1 || s > 10) w.push(`[${b}] will be clamped to 0.1–10 s.`);
    } else if (b.toLowerCase() !== 'break') w.push(`[${b}] isn't a known tag, so it will be read aloud.`);
  }
  return w.join(' ');
}

export type DiffKind = 'same' | 'del' | 'ins';
export type DiffPart = { kind: DiffKind; text: string };

/** Word-level LCS diff, merged into runs. */
export function wordDiff(a: string, b: string): DiffPart[] {
  const A = a.split(/(\s+)/),
    B = b.split(/(\s+)/);
  if (A.length * B.length > 400000)
    return [
      { kind: 'del', text: a },
      { kind: 'ins', text: b },
    ];
  const L = Array.from({ length: A.length + 1 }, () => new Uint16Array(B.length + 1));
  for (let x = A.length - 1; x >= 0; x--)
    for (let y = B.length - 1; y >= 0; y--)
      L[x][y] = A[x] === B[y] ? L[x + 1][y + 1] + 1 : Math.max(L[x + 1][y], L[x][y + 1]);
  const out: DiffPart[] = [];
  const push = (kind: DiffKind, text: string) => {
    const last = out[out.length - 1];
    if (last && last.kind === kind) last.text += text;
    else out.push({ kind, text });
  };
  let x = 0,
    y = 0;
  while (x < A.length && y < B.length) {
    if (A[x] === B[y]) {
      push('same', A[x]);
      x++;
      y++;
    } else if (L[x + 1][y] >= L[x][y + 1]) push('del', A[x++]);
    else push('ins', B[y++]);
  }
  while (x < A.length) push('del', A[x++]);
  while (y < B.length) push('ins', B[y++]);
  return out;
}

/** Diff runs ready to show: changed words are marked, the spaces around them are plain. */
export function diffView(a: string, b: string): DiffPart[] {
  const view: DiffPart[] = [];
  for (const { kind, text } of wordDiff(a, b)) {
    if (kind === 'same' || !text.trim()) {
      view.push({ kind: 'same', text });
      continue;
    }
    const lead = text.match(/^\s*/)?.[0] ?? '';
    const tail = text.match(/\s*$/)?.[0] ?? '';
    if (lead) view.push({ kind: 'same', text: lead });
    view.push({ kind, text: text.trim() });
    if (tail) view.push({ kind: 'same', text: tail });
  }
  return view;
}

export const TAG_RE = /\[[^\]\n[]{1,40}\]/g;
export const tagsOf = (t: string): string[] => t.match(TAG_RE) ?? [];

/** Picks a voice per speaker: known cast first, then starred and stock voices alternating genders. */
export function pickVoices(names: string[], catalog: Voice[], cast: Record<string, string>): Record<string, string> {
  const stock = catalog.filter((v) => v.kind === 'stock' && /^[ab]/.test(v.id));
  const order = [...catalog.filter((v) => v.starred), ...stock.filter((v) => !v.starred)];
  const f = order.filter((v) => v.gender === 'female'),
    m = order.filter((v) => v.gender !== 'female');
  const mixed: Voice[] = [];
  for (let k = 0; k < Math.max(f.length, m.length); k++) {
    if (f[k]) mixed.push(f[k]);
    if (m[k]) mixed.push(m[k]);
  }
  const used = new Set<string>();
  const out: Record<string, string> = {};
  for (const n of names) {
    const known = cast[n.toLowerCase()];
    const v =
      (known && catalog.some((c) => c.id === known) && known) ||
      (mixed.find((c) => !used.has(c.id)) ?? mixed[0] ?? { id: 'af_heart' }).id;
    used.add(v);
    out[n] = v;
  }
  return out;
}

export const fmtDb = (v: number | null | undefined): string => (v == null ? '—' : v.toFixed(1));

export const clampNum = (v: unknown, lo: number, hi: number): number => Math.min(hi, Math.max(lo, Number(v) || 0));
