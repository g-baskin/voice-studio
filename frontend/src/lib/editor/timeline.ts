import type { Clip, Layer, Media, Sequence, Track, TrackKind } from './types.ts';

export const FORMATS = [
  { label: 'Landscape 16:9 (1920 × 1080)', width: 1920, height: 1080 },
  { label: 'Vertical 9:16 (1080 × 1920) for Shorts, Reels, TikTok', width: 1080, height: 1920 },
  { label: 'Square 1:1 (1080 × 1080)', width: 1080, height: 1080 },
  { label: 'Portrait 4:5 (1080 × 1350)', width: 1080, height: 1350 },
  { label: 'HD 720p (1280 × 720)', width: 1280, height: 720 },
  { label: '4K UHD (3840 × 2160)', width: 3840, height: 2160 },
];
export const RATES = [23.976, 24, 25, 29.97, 30, 50, 59.94, 60];
export const MIN_ZOOM = 2;
export const MAX_ZOOM = 400;
export const IMAGE_SECONDS = 5;
export const SNAP_PX = 8;
export const TRACK_HEIGHT = { video: 62, audio: 50 } as const;
export const MIN_TRACK_HEIGHT = 24;
export const MAX_TRACK_HEIGHT = 240;
/** Drag type for media dragged from the bin onto the timeline. */
export const MEDIA_TYPE = 'application/x-editor-media';

export const clipDuration = (c: Clip) => (c.source_out - c.source_in) / c.speed;
export const clipEnd = (c: Clip) => c.start + clipDuration(c);
export const seqDuration = (s: Sequence) => s.clips.reduce((end, c) => Math.max(end, clipEnd(c)), 0);
export const frame = (s: Sequence) => 1 / s.fps;
export const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
export const dbToGain = (db: number) => (db <= -60 ? 0 : 10 ** (db / 20));

/** Snap a time to the sequence's frame grid. */
export const toFrame = (s: Sequence, t: number) => Math.round(t * s.fps) / s.fps;

export function uid(prefix: string): string {
  const bytes = crypto.getRandomValues(new Uint8Array(6));
  return prefix + Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

export function track(kind: TrackKind, name: string, duck = false, id = uid(kind[0])): Track {
  return { id, kind, name, muted: false, hidden: false, locked: false, volume: 0, duck, height: null };
}

export function newSequence(name: string): Sequence {
  return {
    version: 1,
    name,
    width: 1920,
    height: 1080,
    fps: 30,
    duck_db: 12,
    loudness: -14,
    range_in: null,
    range_out: null,
    // Fixed starter ids keep the prerendered page reproducible; added tracks get random ids.
    tracks: [
      track('video', 'V2', false, 'v2'),
      track('video', 'V1', false, 'v1'),
      track('audio', 'A1', false, 'a1'),
      track('audio', 'Music', true, 'a2'),
    ],
    clips: [],
    markers: [],
  };
}

/** HH:MM:SS:FF, as editors show it. */
export function timecode(t: number, fps: number): string {
  const rate = Math.round(fps);
  const total = Math.max(0, Math.round(t * fps));
  const frames = total % rate;
  const secs = Math.floor(total / rate);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${pad(Math.floor(secs / 3600))}:${pad(Math.floor(secs / 60) % 60)}:${pad(secs % 60)}:${pad(frames)}`;
}

export function shortTime(t: number): string {
  const m = Math.floor(t / 60);
  const s = t - m * 60;
  return `${m}:${s.toFixed(1).padStart(4, '0')}`;
}

export const trackHeight = (t: Track) => t.height ?? TRACK_HEIGHT[t.kind];

/** Slip: slide a clip's content under it. Returns the new source in, kept within the media. */
export function slipIn(c: Clip, m: Media | undefined, sourceIn: number): number {
  if (!m || m.kind === 'image') return c.source_in;
  const span = c.source_out - c.source_in;
  return clamp(sourceIn, 0, Math.max(0, (m.duration ?? span) - span));
}

export const onTrack = (s: Sequence, trackId: string) =>
  s.clips.filter((c) => c.track === trackId).sort((a, b) => a.start - b.start);

/** Times an edge can snap to: zero, the playhead, markers, in/out points and other clips' edges. */
export function snapPoints(s: Sequence, playhead: number, exclude: Set<string>): number[] {
  const points = [0, playhead, ...s.markers.map((m) => m.time)];
  if (s.range_in !== null) points.push(s.range_in);
  if (s.range_out !== null) points.push(s.range_out);
  for (const c of s.clips) if (!exclude.has(c.id)) points.push(c.start, clipEnd(c));
  return points;
}

export function snap(t: number, points: number[], threshold: number): { time: number; to: number | null } {
  let best: number | null = null;
  for (const p of points)
    if (Math.abs(p - t) <= threshold && (best === null || Math.abs(p - t) < Math.abs(best - t))) best = p;
  return { time: best ?? t, to: best };
}

/** Split one clip at timeline time t; null when t is not strictly inside it. */
export function splitClip(s: Sequence, c: Clip, t: number): [Clip, Clip] | null {
  const at = toFrame(s, t);
  if (at <= c.start + frame(s) / 2 || at >= clipEnd(c) - frame(s) / 2) return null;
  const cut = c.source_in + (at - c.start) * c.speed;
  const left = { ...c, source_out: cut, fade_out: 0 };
  const right = { ...c, id: uid('c'), start: at, source_in: cut, fade_in: 0, transition: null };
  return [left, right];
}

/** Overwrite edit: clear [start, end) on a track by trimming, splitting or removing other clips there. */
export function clearRange(s: Sequence, trackId: string, start: number, end: number, keep: Set<string>): Clip[] {
  const out: Clip[] = [];
  const eps = 1e-6;
  for (const c of s.clips) {
    const cEnd = clipEnd(c);
    if (c.track !== trackId || keep.has(c.id) || cEnd <= start + eps || c.start >= end - eps) {
      out.push(c);
      continue;
    }
    if (c.start < start - eps) out.push({ ...c, source_out: c.source_in + (start - c.start) * c.speed, fade_out: 0 });
    if (cEnd > end + eps)
      out.push({
        ...c,
        id: c.start < start - eps ? uid('c') : c.id,
        start: end,
        source_in: c.source_in + (end - c.start) * c.speed,
        fade_in: 0,
        transition: null,
      });
  }
  return out.filter((c) => clipDuration(c) >= frame(s) / 2);
}

/** Apply overwrite edits for moved clips, so a track never holds overlapping clips. */
export function settle(s: Sequence, moved: string[]): Clip[] {
  let clips = s.clips;
  for (const id of moved) {
    const c = clips.find((x) => x.id === id);
    if (!c) continue;
    clips = clearRange({ ...s, clips }, c.track, c.start, clipEnd(c), new Set(moved));
  }
  return clips;
}

/** Remove clips and close the gaps they leave on their tracks. */
export function rippleDelete(s: Sequence, ids: Set<string>): Clip[] {
  const removed = s.clips.filter((c) => ids.has(c.id)).sort((a, b) => b.start - a.start);
  let clips = s.clips.filter((c) => !ids.has(c.id));
  for (const gone of removed) {
    const length = clipDuration(gone);
    const end = clipEnd(gone);
    clips = clips.map((c) =>
      c.track === gone.track && c.start >= end - 1e-6 ? { ...c, start: Math.max(0, c.start - length) } : c,
    );
  }
  return clips;
}

export function clipFor(m: Media, trackId: string, start: number): Clip {
  return {
    id: uid('c'),
    track: trackId,
    media: m.id,
    start,
    source_in: 0,
    source_out: m.kind === 'image' ? IMAGE_SECONDS : (m.duration ?? IMAGE_SECONDS),
    speed: 1,
    volume: 0,
    muted: false,
    fade_in: 0,
    fade_out: 0,
    transition: null,
    fit: 'fit',
    scale: 1,
    x: 0,
    y: 0,
    opacity: 1,
  };
}

export const trackKindFor = (m: Media): TrackKind => (m.kind === 'audio' ? 'audio' : 'video');

/** Seconds of unused source before the in point and after the out point, in timeline time. */
export function handles(c: Clip, m: Media | undefined): [number, number] {
  if (!m || m.kind === 'image') return [Infinity, Infinity];
  return [c.source_in / c.speed, Math.max(0, (m.duration ?? 0) - c.source_out) / c.speed];
}

/** Half the usable dissolve, centred on the cut and limited by both clips' handles. */
export function transitionHalf(prev: Clip, pm: Media | undefined, c: Clip, m: Media | undefined, fps: number) {
  if (!c.transition || Math.abs(clipEnd(prev) - c.start) > 1 / fps) return 0;
  const half = Math.min(
    c.transition.duration / 2,
    handles(prev, pm)[1],
    handles(c, m)[0],
    clipDuration(prev),
    clipDuration(c),
  );
  return half >= 0.5 / fps ? half : 0;
}

/** The previous clip that touches this one, so a dissolve can join them. */
export function adjacentBefore(s: Sequence, c: Clip): Clip | null {
  return onTrack(s, c.track).find((p) => p.id !== c.id && Math.abs(clipEnd(p) - c.start) <= 1 / s.fps) ?? null;
}

export function plan(s: Sequence, media: Map<string, Media>): Layer[] {
  const layers: Layer[] = [];
  const count = s.tracks.length;
  s.tracks.forEach((t, index) => {
    const clips = onTrack(s, t.id);
    const lead = clips.map((c, i) =>
      i ? transitionHalf(clips[i - 1], media.get(clips[i - 1].media), c, media.get(c.media), s.fps) : 0,
    );
    clips.forEach((c, i) => {
      const m = media.get(c.media);
      if (!m || m.status !== 'ready') return;
      const tail = i + 1 < clips.length ? lead[i + 1] : 0;
      const picture = t.kind === 'video' && m.kind !== 'audio' && !t.hidden;
      const sound = m.has_audio && !c.muted && !t.muted;
      if (!picture && !sound) return;
      layers.push({
        clip: c,
        media: m,
        z: count - 1 - index,
        t0: c.start - lead[i],
        t1: clipEnd(c) + tail,
        src0: c.source_in - lead[i] * c.speed,
        fadeIn: lead[i] ? 2 * lead[i] : c.fade_in,
        fadeOut: tail ? 0 : c.fade_out,
        afadeIn: lead[i] ? 2 * lead[i] : c.fade_in,
        afadeOut: tail ? 2 * tail : c.fade_out,
        picture,
        sound,
        gainDb: c.volume + t.volume,
        duck: t.kind === 'audio' && t.duck,
      });
    });
  });
  return layers.sort((a, b) => a.z - b.z || a.t0 - b.t0);
}

function ramp(t: number, l: Layer, fadeIn: number, fadeOut: number): number {
  let v = 1;
  if (fadeIn > 0) v = Math.min(v, (t - l.t0) / fadeIn);
  if (fadeOut > 0) v = Math.min(v, (l.t1 - t) / fadeOut);
  return clamp(v, 0, 1);
}

export const pictureAlpha = (l: Layer, t: number) => l.clip.opacity * ramp(t, l, l.fadeIn, l.fadeOut);
export const soundGain = (l: Layer, t: number) => dbToGain(l.gainDb) * ramp(t, l, l.afadeIn, l.afadeOut);
export const sourceTime = (l: Layer, t: number) => Math.max(0, l.src0 + (t - l.t0) * l.clip.speed);

/** Picture size and offset on the frame, as fractions of the sequence size (editor.placement). */
export function placement(s: Sequence, c: Clip, m: Media) {
  const base = (c.fit === 'fit' ? Math.min : Math.max)(s.width / m.width, s.height / m.height);
  const w = (m.width * base * c.scale) / s.width;
  const h = (m.height * base * c.scale) / s.height;
  return { w, h, x: (1 - w) / 2 + c.x, y: (1 - h) / 2 + c.y };
}

/** Limits for dragging a clip edge: the source's length and the neighbouring clips on the track. */
export function trimLimits(s: Sequence, c: Clip, m: Media | undefined, edge: 'start' | 'end'): [number, number] {
  const others = onTrack(s, c.track).filter((o) => o.id !== c.id);
  const minLen = frame(s);
  if (edge === 'start') {
    const prevEnd = Math.max(0, ...others.filter((o) => clipEnd(o) <= c.start + 1e-6).map(clipEnd));
    const earliest = m && m.kind !== 'image' ? c.start - c.source_in / c.speed : -Infinity;
    return [Math.max(prevEnd, earliest, 0), clipEnd(c) - minLen];
  }
  const nextStart = Math.min(Infinity, ...others.filter((o) => o.start >= clipEnd(c) - 1e-6).map((o) => o.start));
  const latest = m && m.kind !== 'image' ? c.start + ((m.duration ?? 0) - c.source_in) / c.speed : Infinity;
  return [c.start + minLen, Math.min(nextStart, latest)];
}

/** Points where the picture or sound changes, for jumping between edits. */
export function editPoints(s: Sequence): number[] {
  const set = new Set<number>([0]);
  for (const c of s.clips) {
    set.add(Math.round(c.start * 1000) / 1000);
    set.add(Math.round(clipEnd(c) * 1000) / 1000);
  }
  return [...set].sort((a, b) => a - b);
}

/** Tick spacing for the ruler so labels stay readable at any zoom. */
export function rulerStep(pxPerSecond: number): { major: number; minor: number } {
  const steps = [0.1, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 1800, 3600];
  const major = steps.find((st) => st * pxPerSecond >= 80) ?? 3600;
  const minor =
    steps
      .slice()
      .reverse()
      .find((st) => st < major && st * pxPerSecond >= 10) ?? major;
  return { major, minor };
}
