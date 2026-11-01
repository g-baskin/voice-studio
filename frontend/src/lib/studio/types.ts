export type Delivery = 'neutral' | 'warm' | 'energetic' | 'calm' | 'serious' | 'excited' | 'soft' | 'custom';
export type Mode = 'sequential' | 'timed';

export type Voice = {
  id: string;
  name: string;
  kind: string;
  gender?: string;
  language?: string;
  starred?: boolean;
};

/** An EQ band: [type, frequency Hz, gain dB]. */
export type EqBand = [string, number, number];

export type Style = {
  id: string;
  name: string;
  speed: number;
  pitch: number;
  gain: number;
  pause: number;
  pause_after: number;
  eq: EqBand[];
};

export type Line = {
  id: string;
  text: string;
  voice: string;
  speaker: string;
  speed: number;
  pitch: number;
  volume: number;
  pause: number;
  delivery: string;
  take: number;
  takes: number[];
  target: number | null;
  start: number | null;
  end: number | null;
  note?: string;
  style?: Style | null;
};

/** The project as the editor holds it; the dictionary stays as editable rows. */
export type EditorProject = {
  title: string;
  lines: Line[];
  dictionary: [string, string][];
  cast: Record<string, string>;
  mode: Mode;
};

/** The project as the server and the draft store it. */
export type ProjectPayload = {
  title: string;
  lines: Line[];
  dictionary: Record<string, string>;
  cast: Record<string, string>;
  mode: Mode;
};

export type ProjectInput = {
  title?: string;
  lines?: Partial<Line>[];
  dictionary?: Record<string, string>;
  cast?: Record<string, string>;
  mode?: string;
};

export type ProjectRecord = { id: string; updated: number; project: ProjectPayload };
export type ProjectSummary = { id: string; title: string; lines: number; updated?: number };

export type Draft = { projectId: string | null; project: ProjectPayload };

export type LlmStatus = {
  available?: boolean;
  via?: string | null;
  provider?: string | null;
  model?: string;
  key_saved?: boolean;
  key_hint?: string;
  env_key?: boolean;
  default_model?: string;
};

export type RewriteStatus = { rules?: boolean; llm?: LlmStatus; tones?: string[] };
export type RewriteResult = { text: string; engine?: string; notes?: string[] };

export type GenStatus = {
  kinds?: Record<string, string>;
  tones?: string[];
  min_seconds?: number;
  max_seconds?: number;
  llm?: LlmStatus;
};
export type GenLine = { speaker: string; text: string };
export type GenResult = {
  title?: string;
  engine?: string;
  estimated_seconds: number;
  words: number;
  notes?: string[];
  lines: GenLine[];
};
export type GenSample = { topic?: string; brief?: string; cta?: string; kind?: string };

export type NoteResult = {
  speed: number;
  pitch: number;
  volume: number;
  pause: number;
  delivery: string;
  tags: string[];
  understood: string[];
  unused: string[];
  text: string;
};

export type ParseResult = {
  lines: (Partial<Line> & { speaker: string })[];
  cast: { speaker: string; voice: string }[];
  warnings: string[];
};

export type RenderFile = { kind: string; name: string; speaker?: string };
export type Loudness = {
  met: boolean;
  target: string;
  note: string;
  measured: {
    lufs: number | null;
    true_peak_db: number | null;
    rms_db: number | null;
    noise_floor_db: number | null;
  };
};
export type Fit = {
  achieved: number;
  target: number;
  met: boolean;
  speed_factor: number;
  stretch: number;
  pause_change: number;
  warnings: string[];
};
export type RenderResult = {
  duration: number;
  elapsed: number;
  files: RenderFile[];
  zip: string;
  captions?: { start: number; end: number; text: string }[];
  loudness: Loudness;
  fit?: Fit | null;
  line_fits?: { line: number; achieved: number; target: number; warning?: string }[];
  overlaps?: { message: string }[];
  errors: { line: number; error: string }[];
  warnings: string[];
};
export type RenderJob = {
  status: 'running' | 'done' | 'cancelled' | 'error';
  progress: number;
  step: string;
  error?: string | null;
  result?: RenderResult;
};
export type RecentRender = { job: string; title: string; created: number; status: string; duration?: number };

export type StatusKey = 'proj' | 'paste' | 'gen' | 'ai' | 'render';
export type Status = { text: string; bad: boolean };
