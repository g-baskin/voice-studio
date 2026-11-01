export type VoiceKind = 'stock' | 'custom' | 'clone';

export type MixPart = { id: string; weight: number };
export type Recipe = { voices: MixPart[]; controls?: { gender?: number } };

export type LibVoice = {
  id: string;
  name: string;
  kind: VoiceKind;
  language: string;
  gender: string;
  starred?: boolean;
  editable?: boolean;
  meta?: { recipe?: Recipe; source?: string };
};

export type Library = { voices: LibVoice[]; languages: string[] };

export type DescribeOption = { recipe: Recipe; summary: string };
export type DescribeResult = { understood: string[]; notes: string[]; options: DescribeOption[] };

export type MatchResult = {
  seconds: number;
  tries: number;
  kept: number;
  before: number;
  after: number;
  best_stock: { id: string; similarity: number }[];
};
export type MatchStatus = {
  status: 'running' | 'done' | 'cancelled' | 'error';
  progress?: number;
  step?: string;
  similarity?: number | null;
  elapsed: number;
  error?: string;
  result?: MatchResult;
};

export type CatalogVoice = { id: string; name: string; kind: string };

export type CloneStatus = {
  installed?: boolean;
  warm?: boolean;
  model?: string;
  license?: string;
  sample_rate?: number;
  device?: string;
  languages?: unknown;
  emotion_tags?: unknown;
};
export type CloneLanguage = { code: string; name: string };
export type CloneJob = {
  status: string;
  progress?: number;
  step?: string;
  error?: string;
  seconds?: number;
  render_seconds?: number;
};

/** A status line: its text and whether it reports a problem. */
export type Msg = { text: string; bad: boolean };
export const ok = (text: string): Msg => ({ text, bad: false });
export const bad = (text: string): Msg => ({ text, bad: true });
