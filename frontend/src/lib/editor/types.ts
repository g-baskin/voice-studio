// Mirrors naturalvoice.editor: the server validates every sequence with the same field names.
export type MediaKind = 'video' | 'audio' | 'image';
export type MediaStatus = 'uploading' | 'processing' | 'ready' | 'error';

export type Thumbs = { count: number; interval: number; width: number; height: number };

export type Media = {
  id: string;
  name: string;
  kind: MediaKind;
  status: MediaStatus;
  error: string | null;
  created: number;
  size: number;
  duration: number | null;
  width: number;
  height: number;
  fps: number;
  has_audio: boolean;
  has_video: boolean;
  thumbs: Thumbs | null;
  peaks_per_second: number;
};

export type TrackKind = 'video' | 'audio';

export type Track = {
  id: string;
  kind: TrackKind;
  name: string;
  muted: boolean;
  hidden: boolean;
  locked: boolean;
  volume: number;
  duck: boolean;
};

export type Transition = { kind: 'dissolve'; duration: number };

export type Clip = {
  id: string;
  track: string;
  media: string;
  start: number;
  source_in: number;
  source_out: number;
  speed: number;
  volume: number;
  muted: boolean;
  fade_in: number;
  fade_out: number;
  transition: Transition | null;
  fit: 'fit' | 'fill';
  scale: number;
  x: number;
  y: number;
  opacity: number;
};

export type Marker = { time: number; label: string };

export type Sequence = {
  version: 1;
  name: string;
  width: number;
  height: number;
  fps: number;
  duck_db: number;
  loudness: number | null;
  range_in: number | null;
  range_out: number | null;
  tracks: Track[];
  clips: Clip[];
  markers: Marker[];
};

export type SequenceSummary = { id: string; name: string; updated: number };

export type ExportJob = {
  id: string;
  status: 'running' | 'done' | 'error' | 'cancelled';
  progress: number;
  error: string | null;
  name: string;
  created: number;
};

/** One clip's part in playback, including dissolve handles (same rules as editor.plan on the server). */
export type Layer = {
  clip: Clip;
  media: Media;
  z: number;
  t0: number;
  t1: number;
  src0: number;
  fadeIn: number;
  fadeOut: number;
  afadeIn: number;
  afadeOut: number;
  picture: boolean;
  sound: boolean;
  gainDb: number;
  duck: boolean;
};
