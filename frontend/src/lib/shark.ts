export type Readout = { tag: string; status: 'applied' | 'approximated' | 'unavailable' | 'unknown'; how: string };
export type Version = { version: number; take: number; note: string; seconds: number };
export type ChunkView = {
  index: number;
  speaker: string;
  voice: string;
  text: string;
  readout: Readout[];
  pause_after: number;
  controls: { speed: number; pitch: number; volume: number; delivery: string };
  state: 'waiting' | 'rendering' | 'ready' | 'error';
  error: string | null;
  versions: Version[];
  selected: number | null;
};
export type JobView = {
  job: string;
  status: 'running' | 'done' | 'cancelled' | 'error';
  error: string | null;
  chunks: ChunkView[];
};
export type Voice = { id: string; name: string; kind: string; language: string };
export type DirectionInfo = { tag: string; exact: boolean };

export const STATUS_LABEL: Record<Readout['status'], string> = {
  applied: 'Applied',
  approximated: 'Approximated',
  unavailable: 'Not available',
  unknown: 'Not recognised',
};

export const SAMPLE = `Narrator: [calm] The harbour was quiet that night.
Mara: [whisper] Did you hear that?
Jonah: [excited] It's the boat! They made it back!
Mara: [sad] Not all of them.`;

/** Speaker names in script order, as written; the server matches them case-insensitively. */
export function speakersIn(script: string): string[] {
  const names = new Map<string, string>();
  for (const line of script.split('\n')) {
    const m = /^\s*([A-Za-z][\w .'-]{0,39}?)\s*:\s+\S/.exec(line);
    if (m && !names.has(m[1].trim().toLowerCase())) names.set(m[1].trim().toLowerCase(), m[1].trim());
  }
  return [...names.values()];
}

/** Turns script speakers into a cast, keeping earlier choices and offering a different voice for each new speaker. */
export function castFor(script: string, previous: Record<string, string>, voices: Voice[]): Record<string, string> {
  const names = speakersIn(script);
  const pool = voices.filter((v) => v.kind === 'stock').map((v) => v.id);
  const cast: Record<string, string> = {};
  let i = 0;
  for (const name of names) {
    const key = name.toLowerCase();
    cast[key] = previous[key] ?? pool[i % Math.max(pool.length, 1)] ?? 'af_heart';
    i += 1;
  }
  return cast;
}
