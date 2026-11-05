import type { Clip, Layer, MarkerColor, Media, Sequence, Track, TrackKind } from './types.ts';

export const FORMATS = [
  { label: 'Landscape 16:9 (1920 × 1080)', width: 1920, height: 1080 },
  { label: 'Vertical 9:16 (1080 × 1920) for Shorts, Reels, TikTok', width: 1080, height: 1920 },
  { label: 'Square 1:1 (1080 × 1080)', width: 1080, height: 1080 },
  { label: 'Portrait 4:5 (1080 × 1350)', width: 1080, height: 1350 },
  { label: 'HD 720p (1280 × 720)', width: 1280, height: 720 },
  { label: '4K UHD (3840 × 2160)', width: 3840, height: 2160 },
];
/** Marker colours as drawn on the ruler and in lists; readable on light and dark themes. */
export const MARKER_HEX: Record<MarkerColor, string> = {
  green: '#3fae5b',
  red: '#d9534f',
  purple: '#8e6bd8',
  orange: '#e8913a',
  yellow: '#d9b52c',
  white: '#b9bfbc',
  blue: '#4a8fe0',
  cyan: '#2fb5c0',
};
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
    subclips: [],
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

// ------------------------------------------------------------------ clip mode: three-point editing and trims
const EPS = 1e-6;

/** What the source viewer offers: one media file, its optional marks, and which halves to use. */
export type SourcePick = { media: Media; in: number | null; out: number | null; video: boolean; audio: boolean };
/** The tracks a source edit lands on (Premiere's source patching). */
export type Targets = { video: string | null; audio: string | null };
/** A resolved three-point edit: the source span and where it lands. */
export type EditSpan = { at: number; source_in: number; source_out: number };

const sourceLength = (m: Media) => (m.kind === 'image' ? Infinity : (m.duration ?? 0));
const defaultOut = (m: Media) => (m.kind === 'image' ? IMAGE_SECONDS : (m.duration ?? IMAGE_SECONDS));

/** The source in point that ends a span of `length` at `out` (back-timing). */
export const backTime = (out: number, length: number) => Math.max(0, out - length);

/**
 * Premiere's three-point rules. Sequence In and Out with one source mark fill that span (forwards from a
 * source In, back-timed from a source Out); with both source marks the source is cut to fit the span.
 * Otherwise the clip lands at the sequence In, ends at the sequence Out, or starts at the playhead.
 */
export function threePoint(s: Sequence, src: SourcePick, playhead: number): EditSpan | null {
  const m = src.media;
  const limit = sourceLength(m);
  const f = frame(s);
  let srcIn = src.in ?? 0;
  let srcOut = src.out ?? defaultOut(m);
  let at: number;
  if (s.range_in !== null && s.range_out !== null) {
    const span = s.range_out - s.range_in;
    at = s.range_in;
    if (src.in === null && src.out !== null) {
      srcIn = backTime(srcOut, span);
      at = s.range_out - (srcOut - srcIn);
    } else srcOut = Math.min(srcIn + span, src.out ?? limit, limit);
  } else if (s.range_in !== null) at = s.range_in;
  else if (s.range_out !== null) at = s.range_out - (srcOut - srcIn);
  else at = playhead;
  srcOut = Math.min(srcOut, limit);
  if (at < 0) {
    srcIn -= at;
    at = 0;
  }
  if (srcOut - srcIn < f / 2) return null;
  return { at: toFrame(s, at), source_in: srcIn, source_out: srcOut };
}

/** The clips a source edit places: the picture (carrying its sound unless audio is off) or the sound alone. */
export function sourceClips(src: SourcePick, span: EditSpan, targets: Targets): Clip[] {
  const m = src.media;
  const make = (trackId: string, muted: boolean) => ({
    ...clipFor(m, trackId, span.at),
    source_in: span.source_in,
    source_out: span.source_out,
    muted,
  });
  const picture = m.kind !== 'audio' && src.video;
  const sound = m.has_audio && src.audio;
  if (picture && targets.video) return [make(targets.video, !sound)];
  if (sound && targets.audio) return [make(targets.audio, false)];
  return [];
}

/** Split clips on these tracks that straddle t, so an edit can open or close a gap there. */
function cutAt(s: Sequence, clips: Clip[], tracks: Set<string>, t: number): Clip[] {
  return clips.flatMap((c) => (tracks.has(c.track) && splitClip(s, c, t)) || [c]);
}

/** Insert edit: open a gap at the clips' start on every given track (sync), then place the clips. */
export function insertEdit(s: Sequence, added: Clip[], tracks: Set<string>): Clip[] {
  if (!added.length) return s.clips;
  const at = Math.min(...added.map((c) => c.start));
  const length = Math.max(...added.map(clipEnd)) - at;
  const shifted = cutAt(s, s.clips, tracks, at).map((c) =>
    tracks.has(c.track) && c.start >= at - frame(s) / 2 ? { ...c, start: c.start + length } : c,
  );
  return [...shifted, ...added];
}

/** Overwrite edit: the clips replace whatever is under them; nothing else moves. */
export function overwriteEdit(s: Sequence, added: Clip[]): Clip[] {
  return settle(
    { ...s, clips: [...s.clips, ...added] },
    added.map((c) => c.id),
  );
}

/** Lift: remove [a, b) from the given tracks and leave a gap. */
export function liftRange(s: Sequence, a: number, b: number, tracks: Set<string>): Clip[] {
  let clips = s.clips;
  for (const id of tracks) clips = clearRange({ ...s, clips }, id, a, b, new Set());
  return clips;
}

/** Extract: remove [a, b) from the given tracks and close the gap. */
export function extractRange(s: Sequence, a: number, b: number, tracks: Set<string>): Clip[] {
  return liftRange(s, a, b, tracks).map((c) =>
    tracks.has(c.track) && c.start >= b - EPS ? { ...c, start: Math.max(0, c.start - (b - a)) } : c,
  );
}

/** Edit points on the given tracks, without the sequence start. */
function cutsOn(s: Sequence, tracks: Set<string>): number[] {
  return editPoints({ ...s, clips: s.clips.filter((c) => tracks.has(c.track)) });
}

/** The edit point closest to t (Resolve's smart insert point). */
export function nearestEdit(s: Sequence, t: number, tracks: Set<string>): number {
  return cutsOn(s, tracks).reduce((best, p) => (Math.abs(p - t) < Math.abs(best - t) ? p : best), 0);
}

/**
 * Premiere's Q and W: trim the previous (or next) edit to the playhead on the given tracks. With ripple the
 * gap closes; without it the gap stays. Returns the clips and the edit used, or null when there is none.
 */
export function trimToPlayhead(
  s: Sequence,
  t: number,
  side: 'previous' | 'next',
  tracks: Set<string>,
  ripple: boolean,
): { clips: Clip[]; edge: number } | null {
  const cuts = cutsOn(s, tracks);
  const half = frame(s) / 2;
  const edge = side === 'previous' ? cuts.filter((p) => p < t - half).at(-1) : cuts.find((p) => p > t + half);
  if (edge === undefined) return null;
  const [a, b] = side === 'previous' ? [edge, t] : [t, edge];
  return { clips: (ripple ? extractRange : liftRange)(s, a, b, tracks), edge };
}

/** Room to move a clip's edges: earliest start and latest end its media allows, in timeline time. */
function reach(c: Clip, m: Media | undefined): [number, number] {
  const [head, tail] = handles(c, m);
  return [c.start - head, clipEnd(c) + tail];
}

/** Ripple trim one edge: the clip keeps its start, and later clips on its track follow the length change. */
export function rippleEdge(s: Sequence, c: Clip, m: Media | undefined, edge: 'start' | 'end', t: number): Clip[] {
  const f = frame(s);
  const [earliest, latest] = reach(c, m);
  // How much the clip's end, and everything after it on the track, moves.
  const delta =
    edge === 'end' ? clamp(t, c.start + f, latest) - clipEnd(c) : c.start - clamp(t, earliest, clipEnd(c) - f);
  if (Math.abs(delta) < EPS) return s.clips;
  const end = clipEnd(c);
  return s.clips.map((x) => {
    if (x.id === c.id)
      return edge === 'end'
        ? { ...x, source_out: x.source_out + delta * x.speed }
        : { ...x, source_in: x.source_in - delta * x.speed };
    return x.track === c.track && x.start >= end - EPS ? { ...x, start: Math.max(0, x.start + delta) } : x;
  });
}

/** Roll: move the cut between two touching clips; the total length stays the same. */
export function rollEdit(
  s: Sequence,
  left: Clip,
  lm: Media | undefined,
  right: Clip,
  rm: Media | undefined,
  t: number,
): Clip[] {
  const f = frame(s);
  const cut = clamp(t, Math.max(left.start + f, reach(right, rm)[0]), Math.min(clipEnd(right) - f, reach(left, lm)[1]));
  return s.clips.map((x) => {
    if (x.id === left.id) return { ...x, source_out: x.source_in + (cut - x.start) * x.speed };
    if (x.id === right.id) return { ...x, start: cut, source_in: x.source_in + (cut - x.start) * x.speed };
    return x;
  });
}

/** Slide: move a clip between its neighbours, which lengthen or shorten to fill; its own content stays. */
export function slideClip(s: Sequence, c: Clip, media: Map<string, Media>, delta: number): Clip[] {
  const f = frame(s);
  const others = onTrack(s, c.track).filter((o) => o.id !== c.id);
  const prev = others.filter((o) => clipEnd(o) <= c.start + EPS).at(-1) ?? null;
  const next = others.find((o) => o.start >= clipEnd(c) - EPS) ?? null;
  const prevTouch = prev && Math.abs(clipEnd(prev) - c.start) <= f / 2 ? prev : null;
  const nextTouch = next && Math.abs(next.start - clipEnd(c)) <= f / 2 ? next : null;
  let lo = prevTouch ? -(clipDuration(prevTouch) - f) : -(c.start - (prev ? clipEnd(prev) : 0));
  let hi = nextTouch ? clipDuration(nextTouch) - f : next ? next.start - clipEnd(c) : Infinity;
  if (prevTouch) hi = Math.min(hi, handles(prevTouch, media.get(prevTouch.media))[1]);
  if (nextTouch) lo = Math.max(lo, -handles(nextTouch, media.get(nextTouch.media))[0]);
  const d = clamp(delta, Math.min(0, lo), Math.max(0, hi));
  if (Math.abs(d) < EPS) return s.clips;
  return s.clips.map((x) => {
    if (x.id === c.id) return { ...x, start: x.start + d };
    if (x.id === prevTouch?.id) return { ...x, source_out: x.source_out + d * x.speed };
    if (x.id === nextTouch?.id) return { ...x, start: x.start + d, source_in: x.source_in + d * x.speed };
    return x;
  });
}

/** Extend the clip edge nearest t to t (Premiere's E), within its media and its neighbours. */
export function extendEdge(s: Sequence, c: Clip, m: Media | undefined, t: number): Clip | null {
  const edge = Math.abs(t - c.start) <= Math.abs(t - clipEnd(c)) ? 'start' : 'end';
  const [lo, hi] = trimLimits(s, c, m, edge);
  const to = clamp(toFrame(s, t), lo, hi);
  if (edge === 'end') return { ...c, source_out: c.source_in + (to - c.start) * c.speed };
  return { ...c, start: to, source_in: c.source_in + (to - c.start) * c.speed };
}

export const SHUTTLE_RATES = [1, 2, 4, 8];

/** J/K/L shuttle: each press in the same direction doubles up to 8×; the other direction starts again at 1×. */
export function nextShuttleRate(rate: number, key: 'j' | 'k' | 'l'): number {
  if (key === 'k') return 0;
  const sign = key === 'l' ? 1 : -1;
  if (Math.sign(rate) !== sign) return sign;
  return sign * Math.min(SHUTTLE_RATES.at(-1)!, Math.abs(rate) * 2);
}

/** Timeline times where a source time of this clip's media appears, or null when the clip doesn't use it. */
export function sourceToTimeline(c: Clip, sourceTime: number): number | null {
  if (sourceTime < c.source_in - EPS || sourceTime > c.source_out + EPS) return null;
  return c.start + (sourceTime - c.source_in) / c.speed;
}

/**
 * Timeline spans to cut for the silent stretches of each clip's media: each kept `padding` seconds from
 * the speech either side, and ignored when shorter than `least`. Sorted, merged and inside the clips.
 */
export function silenceCuts(clips: Clip[], silences: [number, number][], padding: number, least: number): SilenceCut[] {
  const cuts = new Map<string, SilenceCut>();
  for (const c of clips) {
    const spans: [number, number][] = [];
    for (const [a, b] of silences) {
      const lo = Math.max(a, c.source_in) + (a > c.source_in + EPS ? padding : 0);
      const hi = Math.min(b, c.source_out) - (b < c.source_out - EPS ? padding : 0);
      if ((hi - lo) / c.speed < least) continue;
      spans.push([c.start + (lo - c.source_in) / c.speed, c.start + (hi - c.source_in) / c.speed]);
    }
    spans.sort((x, y) => x[0] - y[0]);
    const merged: [number, number][] = [];
    for (const span of spans) {
      const last = merged.at(-1);
      if (last && span[0] <= last[1] + EPS) last[1] = Math.max(last[1], span[1]);
      else merged.push([...span]);
    }
    // A span is cut only from tracks whose own clip is silent there; equal spans share one cut.
    for (const [a, b] of merged) {
      const key = `${a.toFixed(4)}-${b.toFixed(4)}`;
      const cut = cuts.get(key);
      if (!cut) cuts.set(key, [a, b, [c.track]]);
      else if (!cut[2].includes(c.track)) cut[2].push(c.track);
    }
  }
  return [...cuts.values()].sort((x, y) => x[0] - y[0] || x[1] - y[1]);
}

/** Clips playing the same source moments as one of the chosen clips (linked picture and sound). */
export function linkedClips(all: Clip[], chosen: Clip[]): Clip[] {
  const key = (c: Clip) => `${c.media}|${(c.start - c.source_in / c.speed).toFixed(4)}|${c.speed}`;
  const keys = new Set(chosen.map(key));
  return all.filter((c) => keys.has(key(c)));
}

/** A timeline span to remove and the tracks whose clips are silent across it. */
export type SilenceCut = [start: number, end: number, tracks: string[]];

/** A part of the sequence to render as its own file. */
export type BatchRange = { in: number; out: number; label: string };

/** Each marker up to the next one (the last runs to the end), skipping spans shorter than a frame. */
export function markerRanges(seq: Sequence, duration: number): BatchRange[] {
  const marks = [...seq.markers].sort((a, b) => a.time - b.time);
  const out: BatchRange[] = [];
  marks.forEach((m, i) => {
    const end = Math.min(marks[i + 1]?.time ?? duration, duration);
    if (end - m.time >= 1 / seq.fps) out.push({ in: m.time, out: end, label: m.label });
  });
  return out;
}

/**
 * Where each subclip plays in the sequence: the first clip of its media that shows any of it, clipped to
 * the subclip's part. Subclips not used in the sequence are left out and counted.
 */
export function subclipRanges(seq: Sequence): { ranges: BatchRange[]; unused: number } {
  const ranges: BatchRange[] = [];
  let unused = 0;
  const clips = [...seq.clips].sort((a, b) => a.start - b.start);
  for (const sub of seq.subclips) {
    const c = clips.find(
      (x) => x.media === sub.media && x.source_in < sub.source_out - EPS && x.source_out > sub.source_in + EPS,
    );
    if (!c) {
      unused++;
      continue;
    }
    const a = sourceToTimeline(c, Math.max(sub.source_in, c.source_in));
    const b = sourceToTimeline(c, Math.min(sub.source_out, c.source_out));
    if (a === null || b === null || b - a < 1 / seq.fps) unused++;
    else ranges.push({ in: a, out: b, label: sub.name });
  }
  return { ranges: ranges.sort((x, y) => x.in - y.in), unused };
}
