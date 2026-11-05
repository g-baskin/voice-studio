import * as api from './api.ts';
import {
  clamp,
  clipEnd,
  clipFor,
  extendEdge,
  extractRange,
  insertEdit,
  liftRange,
  nearestEdit,
  newSequence,
  nextShuttleRate,
  overwriteEdit,
  plan,
  rippleDelete,
  seqDuration,
  settle,
  linkedClips,
  silenceCuts,
  sourceClips,
  sourceToTimeline,
  splitClip,
  threePoint,
  trimToPlayhead,
  MAX_TRACK_HEIGHT,
  MIN_TRACK_HEIGHT,
  toFrame,
  track,
  frame,
  IMAGE_SECONDS,
  TRACK_HEIGHT,
  trackHeight,
  trackKindFor,
  uid,
} from './timeline.ts';
import type { EditSpan, SilenceCut, SourcePick, Targets } from './timeline.ts';
import type {
  Analysis,
  AnalysisKind,
  Clip,
  MarkerColor,
  Media,
  Sequence,
  SequenceSummary,
  Subclip,
  TrackKind,
} from './types.ts';

const HISTORY = 100;
const SAVE_DELAY = 700;
const POLL_MS = 1000;
const ANALYSIS_POLL_MS = 700;
const MAX_SUBCLIPS = 500;
const MAX_MARKERS = 200;
const MODE_KEY = 'editor-mode';
// Longest a still's source can be marked in the source viewer.
const IMAGE_LIMIT = 60;

export type SaveState = 'saved' | 'saving' | 'unsaved' | 'error';
export type Tool = 'select' | 'razor' | 'slip' | 'ripple' | 'roll' | 'slide';
/** Edit is the full editor; Clip puts a source viewer beside the program for fast clipping. */
export type Mode = 'edit' | 'clip';
export type Viewer = 'source' | 'program';
export type SourceEdit = 'insert' | 'overwrite' | 'append' | 'smart';

/** The source viewer: one media file (or subclip) with its own playhead and marks. Not saved or undone. */
export type SourceState = {
  media: string;
  subclip: string | null;
  playhead: number;
  in: number | null;
  out: number | null;
  video: boolean;
  audio: boolean;
  /** Session-only marks dropped with M while the source viewer has focus. */
  markers: number[];
};

/** Two frames shown side by side while trimming: each is a clip and the source time to show. */
export type TrimFrame = { clip: string; time: number };
export type TrimView = { left: TrimFrame | null; right: TrimFrame | null };

/** Everything the Editor page shares: the open sequence, the media bin, selection, playhead and history. */
export class Editor {
  media = $state<Media[]>([]);
  sequences = $state<SequenceSummary[]>([]);
  seq = $state<Sequence>(newSequence('Sequence 1'));
  seqId = $state<string | null>(null);
  selection = $state<string[]>([]);
  selectedTrack = $state<string | null>(null);
  playhead = $state(0);
  playing = $state(false);
  zoom = $state(40);
  tool = $state<Tool>('select');
  snapping = $state(true);
  snapLine = $state<number | null>(null);
  saveState = $state<SaveState>('saved');
  message = $state('');
  messageBad = $state(false);
  uploads = $state(0);
  undoCount = $state(0);
  redoCount = $state(0);
  /** Bumped when a filmstrip or waveform finishes loading, so the timeline redraws. */
  assetVersion = $state(0);
  mode = $state<Mode>('edit');
  /** Which viewer I, O, M and the transport keys act on. */
  viewer = $state<Viewer>('program');
  source = $state<SourceState | null>(null);
  /** Source patching: the tracks source edits land on; null picks the first unlocked one. */
  targets = $state<Targets>({ video: null, audio: null });
  /** J/K/L shuttle rate: 0 stopped, negative plays backwards. */
  shuttle = $state(0);
  trimView = $state<TrimView | null>(null);
  /** Latest analysis per media and kind, keyed `${media}:${kind}`. */
  analyses = $state<Record<string, Analysis>>({});

  mediaById = $derived(new Map(this.media.map((m) => [m.id, m])));
  layers = $derived(plan(this.seq, this.mediaById));
  duration = $derived(seqDuration(this.seq));
  selected = $derived(this.seq.clips.filter((c) => this.selection.includes(c.id)));
  sourceMedia = $derived(this.source ? (this.mediaById.get(this.source.media) ?? null) : null);
  /** The tracks source edits will use, for display; like patched() but never adds a track. */
  targetIds = $derived.by(() => {
    const pick = (kind: TrackKind, id: string | null) => {
      const open = this.seq.tracks.filter((t) => t.kind === kind && !t.locked);
      return (open.find((t) => t.id === id) ?? (kind === 'video' ? open.at(-1) : open[0]))?.id ?? null;
    };
    return { video: pick('video', this.targets.video), audio: pick('audio', this.targets.audio) };
  });

  private past: Sequence[] = [];
  private future: Sequence[] = [];
  private gestureBase: Sequence | null = null;
  private saveTimer: ReturnType<typeof setTimeout> | undefined;
  private pollTimer: ReturnType<typeof setTimeout> | undefined;
  private saving: Promise<void> | null = null;
  private peaks = new Map<string, Uint8Array | null>();
  private thumbs = new Map<string, HTMLImageElement>();
  private analysisTimers = new Map<string, ReturnType<typeof setTimeout>>();

  say(text: string, bad = false) {
    this.message = text;
    this.messageBad = bad;
  }

  fail(error: unknown) {
    this.say(error instanceof Error ? error.message : 'Something went wrong.', true);
  }

  // ------------------------------------------------------------------ history and saving
  private remember(base: Sequence) {
    this.past.push(base);
    if (this.past.length > HISTORY) this.past.shift();
    this.future = [];
    this.undoCount = this.past.length;
    this.redoCount = 0;
    this.changed();
  }

  /** Apply one undoable change. */
  commit(change: (s: Sequence) => void) {
    const base = $state.snapshot(this.seq) as Sequence;
    change(this.seq);
    // An edit that changed nothing leaves no empty undo step.
    if (JSON.stringify(base) !== JSON.stringify($state.snapshot(this.seq))) this.remember(base);
  }

  /** Start a drag: live edits until endGesture() records one undo step. */
  beginGesture() {
    this.gestureBase = $state.snapshot(this.seq) as Sequence;
  }

  endGesture(moved: string[] = []) {
    const base = this.gestureBase;
    this.gestureBase = null;
    this.snapLine = null;
    if (!base) return;
    if (moved.length) this.seq.clips = settle(this.seq, moved);
    if (JSON.stringify(base) !== JSON.stringify($state.snapshot(this.seq))) this.remember(base);
  }

  cancelGesture() {
    if (this.gestureBase) this.seq = this.gestureBase;
    this.gestureBase = null;
    this.snapLine = null;
  }

  undo() {
    const prev = this.past.pop();
    if (!prev) return;
    this.future.push($state.snapshot(this.seq) as Sequence);
    this.seq = prev;
    this.afterHistory();
  }

  redo() {
    const next = this.future.pop();
    if (!next) return;
    this.past.push($state.snapshot(this.seq) as Sequence);
    this.seq = next;
    this.afterHistory();
  }

  private afterHistory() {
    this.undoCount = this.past.length;
    this.redoCount = this.future.length;
    const ids = new Set(this.seq.clips.map((c) => c.id));
    this.selection = this.selection.filter((id) => ids.has(id));
    this.changed();
  }

  private changed() {
    this.saveState = 'unsaved';
    clearTimeout(this.saveTimer);
    this.saveTimer = setTimeout(() => void this.save(), SAVE_DELAY);
  }

  /** Save now; resolves once the server has the current sequence. */
  async save(): Promise<void> {
    clearTimeout(this.saveTimer);
    if (this.saving) await this.saving;
    if (this.saveState === 'saved' && this.seqId) return;
    const body = $state.snapshot(this.seq) as Sequence;
    this.saveState = 'saving';
    this.saving = (async () => {
      try {
        const record = this.seqId ? await api.saveSequence(this.seqId, body) : await api.createSequence(body);
        this.seqId = record.id;
        if (JSON.stringify(body) === JSON.stringify($state.snapshot(this.seq))) this.saveState = 'saved';
        else this.changed();
        this.upsertSummary({ id: record.id, name: record.name, updated: record.updated });
      } catch (error) {
        this.saveState = 'error';
        this.fail(error);
      } finally {
        this.saving = null;
      }
    })();
    await this.saving;
  }

  private upsertSummary(summary: SequenceSummary) {
    this.sequences = [summary, ...this.sequences.filter((s) => s.id !== summary.id)];
  }

  /** Keep-alive save when the page closes; small sequences only (browser limit is 64 KB). */
  flushOnExit() {
    if (this.saveState === 'saved' || !this.seqId) return;
    const body = JSON.stringify($state.snapshot(this.seq));
    if (body.length > 60000) return;
    void fetch(`/api/editor/sequences/${this.seqId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body,
      keepalive: true,
    });
  }

  // ------------------------------------------------------------------ sequences
  async init() {
    try {
      const [media, sequences] = await Promise.all([api.listMedia(), api.listSequences()]);
      this.media = media;
      this.sequences = sequences;
      if (sequences.length) await this.open(sequences[0].id);
      this.poll();
    } catch (error) {
      this.fail(error);
    }
  }

  private reset(seq: Sequence, id: string | null) {
    this.seq = seq;
    this.seqId = id;
    this.past = [];
    this.future = [];
    this.undoCount = 0;
    this.redoCount = 0;
    this.selection = [];
    this.selectedTrack = null;
    this.playhead = 0;
    this.saveState = 'saved';
  }

  async open(id: string) {
    if (id === this.seqId) return;
    await this.save();
    const record = await api.getSequence(id);
    const { id: _id, updated: _updated, ...seq } = record;
    // Sequences saved before subclips and marker colours existed.
    seq.subclips ??= [];
    seq.markers = seq.markers.map((m) => ({ ...m, color: m.color ?? 'green' }));
    this.reset(seq, id);
  }

  async create() {
    await this.save();
    this.reset(newSequence(`Sequence ${this.sequences.length + 1}`), null);
    this.saveState = 'unsaved';
    await this.save();
  }

  async remove() {
    if (!this.seqId) return;
    const gone = this.seqId;
    clearTimeout(this.saveTimer);
    await api.deleteSequence(gone);
    this.sequences = this.sequences.filter((s) => s.id !== gone);
    if (this.sequences.length) {
      this.seqId = null;
      await this.open(this.sequences[0].id);
    } else this.reset(newSequence('Sequence 1'), null);
  }

  // ------------------------------------------------------------------ media bin
  async upload(files: Iterable<File>) {
    for (const file of files) {
      this.uploads += 1;
      this.say(`Uploading ${file.name}...`);
      try {
        const record = await api.uploadMedia(file);
        this.media = [...this.media, record];
        this.say(`${file.name} added. Preparing its preview...`);
      } catch (error) {
        this.fail(error);
      } finally {
        this.uploads -= 1;
      }
    }
    this.poll();
  }

  private poll() {
    clearTimeout(this.pollTimer);
    if (!this.media.some((m) => m.status === 'processing')) return;
    this.pollTimer = setTimeout(async () => {
      try {
        const fresh = await api.listMedia();
        const ready = fresh.filter(
          (m) => m.status !== 'processing' && this.mediaById.get(m.id)?.status === 'processing',
        );
        this.media = fresh;
        for (const m of ready)
          this.say(m.status === 'ready' ? `${m.name} is ready.` : (m.error ?? ''), m.status !== 'ready');
      } catch (error) {
        this.fail(error);
      }
      this.poll();
    }, POLL_MS);
  }

  async removeMedia(m: Media) {
    try {
      await api.removeMedia(m.id);
      this.media = this.media.filter((x) => x.id !== m.id);
      this.say(`${m.name} removed from the bin.`);
    } catch (error) {
      this.fail(error);
    }
  }

  stop() {
    clearTimeout(this.pollTimer);
    clearTimeout(this.saveTimer);
    for (const timer of this.analysisTimers.values()) clearTimeout(timer);
    this.analysisTimers.clear();
  }

  /** A clip's waveform peaks, fetched once; null while loading or when the media has no sound. */
  peaksFor(m: Media): Uint8Array | null {
    if (!m.has_audio || m.status !== 'ready') return null;
    if (!this.peaks.has(m.id)) {
      this.peaks.set(m.id, null);
      void fetch(api.peaksUrl(m.id))
        .then((r) => (r.ok ? r.json() : null))
        .then((body: { peaks: number[] } | null) => {
          if (body) this.peaks.set(m.id, Uint8Array.from(body.peaks));
          this.assetVersion += 1;
        })
        .catch(() => {});
    }
    return this.peaks.get(m.id) ?? null;
  }

  thumbsFor(m: Media): HTMLImageElement | null {
    if (!m.thumbs || m.status !== 'ready') return null;
    let img = this.thumbs.get(m.id);
    if (!img) {
      img = new Image();
      img.onload = () => (this.assetVersion += 1);
      img.src = api.thumbsUrl(m.id);
      this.thumbs.set(m.id, img);
    }
    return img.complete && img.naturalWidth ? img : null;
  }

  // ------------------------------------------------------------------ editing
  isLocked(c: Clip) {
    return this.seq.tracks.find((t) => t.id === c.track)?.locked ?? true;
  }

  /** Track height is a view setting: saved with the sequence but not an undo step. */
  resizeTrack(id: string, height: number) {
    const t = this.seq.tracks.find((x) => x.id === id);
    if (!t) return;
    const next = height === TRACK_HEIGHT[t.kind] ? null : clamp(Math.round(height), MIN_TRACK_HEIGHT, MAX_TRACK_HEIGHT);
    if (t.height === next) return;
    t.height = next;
    this.changed();
  }

  /** Grow or shrink every track by a factor; 0 resets them all. */
  resizeTracks(factor: number) {
    for (const t of this.seq.tracks) this.resizeTrack(t.id, factor ? trackHeight(t) * factor : TRACK_HEIGHT[t.kind]);
  }

  firstTrack(kind: TrackKind): string {
    const found = this.seq.tracks.filter((t) => t.kind === kind && !t.locked);
    // The lowest video track is V1, the one editors fill first.
    const pick = kind === 'video' ? found.at(-1) : found[0];
    return pick?.id ?? this.addTrack(kind);
  }

  addTrack(kind: TrackKind): string {
    const count = this.seq.tracks.filter((t) => t.kind === kind).length;
    const fresh = track(kind, `${kind === 'video' ? 'V' : 'A'}${count + 1}`);
    if (this.seq.tracks.length >= 16) {
      this.say('A sequence can have up to 16 tracks.', true);
      return this.seq.tracks.find((t) => t.kind === kind)?.id ?? '';
    }
    if (kind === 'video') this.seq.tracks.unshift(fresh);
    else this.seq.tracks.push(fresh);
    return fresh.id;
  }

  removeTrack(id: string) {
    const t = this.seq.tracks.find((x) => x.id === id);
    if (!t) return;
    if (this.seq.tracks.filter((x) => x.kind === t.kind).length <= 1) {
      this.say(`Keep at least one ${t.kind} track.`, true);
      return;
    }
    this.commit((s) => {
      s.tracks = s.tracks.filter((x) => x.id !== id);
      s.clips = s.clips.filter((c) => c.track !== id);
    });
    if (this.selectedTrack === id) this.selectedTrack = null;
  }

  /** Place media on the timeline (overwrite edit), on a matching track. */
  place(m: Media, trackId: string | null, start: number) {
    if (m.status !== 'ready') {
      this.say(`${m.name} is not ready yet.`, true);
      return;
    }
    const kind = trackKindFor(m);
    this.commit((s) => {
      const target =
        s.tracks.find((t) => t.id === trackId && t.kind === kind && !t.locked)?.id ?? this.firstTrack(kind);
      const clip = clipFor(m, target, Math.max(0, toFrame(s, start)));
      s.clips.push(clip);
      s.clips = settle(s, [clip.id]);
      this.selection = [clip.id];
    });
  }

  /** Split selected clips at the playhead, or every unlocked clip under it when none is selected. */
  splitAt(t: number, only: Clip[] | null = null) {
    const pool = only ?? (this.selected.length ? this.selected : this.seq.clips);
    const targets = pool.filter((c) => !this.isLocked(c) && c.start < t && clipEnd(c) > t);
    if (!targets.length) {
      this.say('Nothing to split at the playhead.');
      return;
    }
    this.commit((s) => {
      for (const c of targets) {
        const parts = splitClip(s, c, t);
        if (!parts) continue;
        s.clips = s.clips.flatMap((x) => (x.id === c.id ? parts : [x]));
      }
    });
  }

  deleteSelected(ripple: boolean) {
    const ids = new Set(this.selected.filter((c) => !this.isLocked(c)).map((c) => c.id));
    if (!ids.size) return;
    this.commit((s) => {
      s.clips = ripple ? rippleDelete(s, ids) : s.clips.filter((c) => !ids.has(c.id));
    });
    this.selection = [];
  }

  /** Detach a video clip's sound onto an audio track, like unlinking in Premiere Pro. */
  detachAudio(c: Clip) {
    const m = this.mediaById.get(c.media);
    if (!m?.has_audio || m.kind !== 'video') return;
    this.commit((s) => {
      const target = this.firstTrack('audio');
      const sound: Clip = { ...$state.snapshot(c), id: uid('c'), track: target, fit: 'fit', scale: 1, x: 0, y: 0 };
      const original = s.clips.find((x) => x.id === c.id);
      if (original) original.muted = true;
      s.clips.push(sound);
      s.clips = settle(s, [sound.id]);
    });
  }

  addMarker(t: number) {
    const at = toFrame(this.seq, t);
    if (this.seq.markers.some((m) => Math.abs(m.time - at) < 1e-6)) return;
    this.commit((s) => {
      s.markers.push({ time: at, label: `Marker ${s.markers.length + 1}`, color: 'green' });
      s.markers.sort((a, b) => a.time - b.time);
    });
  }

  setIn(t: number) {
    this.commit((s) => {
      s.range_in = toFrame(s, t);
      if (s.range_out !== null && s.range_out <= s.range_in) s.range_out = null;
    });
  }

  setOut(t: number) {
    this.commit((s) => {
      s.range_out = toFrame(s, t);
      if (s.range_in !== null && s.range_in >= s.range_out) s.range_in = null;
    });
  }

  clearInOut() {
    this.commit((s) => {
      s.range_in = null;
      s.range_out = null;
    });
  }

  /** Add a cross dissolve to each selected clip's start (Premiere's Ctrl+D). */
  addDissolve() {
    const ids = this.selected.map((c) => c.id);
    if (!ids.length) {
      this.say('Select the clip after a cut to add a dissolve.');
      return;
    }
    this.commit((s) => {
      for (const c of s.clips) if (ids.includes(c.id)) c.transition = { kind: 'dissolve', duration: 1 };
    });
  }

  // ------------------------------------------------------------------ clip mode
  setMode(mode: Mode) {
    this.mode = mode;
    if (mode === 'edit') this.viewer = 'program';
    try {
      localStorage.setItem(MODE_KEY, mode);
    } catch {
      // Private browsing: the mode just isn't remembered.
    }
  }

  savedMode(): Mode {
    try {
      return localStorage.getItem(MODE_KEY) === 'clip' ? 'clip' : 'edit';
    } catch {
      return 'edit';
    }
  }

  /** Open media (or one of its subclips) in the source viewer. */
  loadSource(m: Media, subclip: Subclip | null = null) {
    if (m.status !== 'ready') {
      this.say(`${m.name} is not ready yet.`, true);
      return;
    }
    const same = this.source?.media === m.id ? this.source : null;
    this.source = {
      media: m.id,
      subclip: subclip?.id ?? null,
      playhead: subclip?.source_in ?? 0,
      in: subclip?.source_in ?? null,
      out: subclip?.source_out ?? null,
      video: same?.video ?? true,
      audio: same?.audio ?? true,
      markers: same?.markers ?? [],
    };
    this.viewer = 'source';
    if (this.mode !== 'clip') this.setMode('clip');
  }

  /** Source length in seconds; stills can be any length, so their marks are free. */
  sourceLength(): number {
    const m = this.sourceMedia;
    if (!m) return 0;
    return m.kind === 'image' ? Math.max(IMAGE_LIMIT, this.source?.out ?? 0) : (m.duration ?? 0);
  }

  seekSource(t: number) {
    if (this.source) this.source.playhead = clamp(t, 0, this.sourceLength());
  }

  setSourceIn(t: number) {
    const src = this.source;
    if (!src) return;
    src.in = clamp(t, 0, this.sourceLength());
    if (src.out !== null && src.out <= src.in) src.out = null;
  }

  setSourceOut(t: number) {
    const src = this.source;
    if (!src) return;
    src.out = clamp(t, 0, this.sourceLength());
    if (src.in !== null && src.in >= src.out) src.in = null;
  }

  clearSourceMarks() {
    if (!this.source) return;
    this.source.in = null;
    this.source.out = null;
  }

  /** Premiere's Mark Clip (X): set the sequence In/Out around the clip under the playhead. */
  markClip() {
    const t = this.playhead;
    const pool = this.selected.length ? this.selected : this.seq.clips;
    const under = pool.filter((c) => c.start <= t + 1e-6 && clipEnd(c) > t + 1e-6);
    if (!under.length) {
      this.say('No clip under the playhead to mark.');
      return;
    }
    this.commit((s) => {
      s.range_in = toFrame(s, Math.min(...under.map((c) => c.start)));
      s.range_out = toFrame(s, Math.max(...under.map(clipEnd)));
    });
  }

  sourcePick(): SourcePick | null {
    const src = this.source;
    const m = this.sourceMedia;
    if (!src || !m) return null;
    return { media: m, in: src.in, out: src.out, video: src.video, audio: src.audio };
  }

  /** Unlocked tracks: the ones an edit may cut or move. */
  unlocked(): Set<string> {
    return new Set(this.seq.tracks.filter((t) => !t.locked).map((t) => t.id));
  }

  /** Patched tracks, falling back to the first unlocked track of each kind (added if there is none). */
  /** The target tracks for this source; only the kind the edit uses is resolved, so no unused track is added. */
  private patched(src: SourcePick): Targets {
    const pick = (kind: TrackKind, id: string | null) =>
      this.seq.tracks.find((t) => t.id === id && t.kind === kind && !t.locked)?.id ?? this.firstTrack(kind);
    const picture = src.media.kind !== 'audio' && src.video;
    const sound = src.media.has_audio && src.audio;
    return {
      video: picture ? pick('video', this.targets.video) : null,
      audio: !picture && sound ? pick('audio', this.targets.audio) : null,
    };
  }

  /** One video and one audio target, like Premiere's source patching; the track must be unlocked. */
  setTarget(kind: TrackKind, id: string) {
    const t = this.seq.tracks.find((x) => x.id === id);
    if (!t || t.kind !== kind) return;
    if (t.locked) {
      this.say(`Unlock ${t.name} to target it.`, true);
      return;
    }
    this.targets = { ...this.targets, [kind]: id };
    this.say(`Source ${kind === 'video' ? 'picture' : 'sound'} goes to ${t.name}.`);
  }

  /** Insert (,), Overwrite (.), Append to end (Shift+.) or Smart Insert at the nearest edit (Shift+,). */
  sourceEdit(kind: SourceEdit) {
    const src = this.sourcePick();
    if (!src) {
      this.say('Open a clip in the source viewer first: double-click it in the bin.', true);
      return;
    }
    if (!src.video && !src.audio) {
      this.say('Turn on the source picture or sound first.', true);
      return;
    }
    const s0 = this.seq;
    const free = kind === 'append' || kind === 'smart';
    // Append and smart insert ignore the sequence In/Out; they choose the spot themselves.
    const marks = free ? { ...s0, range_in: null, range_out: null } : s0;
    const at =
      kind === 'append'
        ? this.duration
        : kind === 'smart'
          ? nearestEdit(s0, this.playhead, this.unlocked())
          : this.playhead;
    const span: EditSpan | null = threePoint(marks, src, at);
    if (!span) {
      this.say('The source In and Out are too close together.', true);
      return;
    }
    let placed: Clip[] = [];
    this.commit((s) => {
      placed = sourceClips(src, span, this.patched(src));
      if (!placed.length) return;
      s.clips = kind === 'overwrite' ? overwriteEdit(s, placed) : insertEdit(s, placed, this.unlocked());
    });
    if (!placed.length) {
      this.say(`The source has no ${src.video ? 'picture' : 'sound'} to place on that track.`, true);
      return;
    }
    this.selection = placed.map((c) => c.id);
    this.playhead = Math.max(...placed.map(clipEnd));
    this.viewer = 'program';
  }

  private needRange(): [number, number] | null {
    const { range_in: a, range_out: b } = this.seq;
    if (a === null || b === null) {
      this.say('Set the sequence In and Out first (I and O).', true);
      return null;
    }
    return [a, b];
  }

  /** Lift (;) leaves a gap; Extract (') closes it. Both act on every unlocked track. */
  liftOrExtract(close: boolean) {
    const range = this.needRange();
    if (!range) return;
    this.commit((s) => {
      s.clips = (close ? extractRange : liftRange)(s, range[0], range[1], this.unlocked());
      if (close) {
        s.range_in = null;
        s.range_out = null;
      }
    });
    this.playhead = range[0];
    this.selection = [];
  }

  /** Q / W (ripple) and Alt+Q / Alt+W (leave a gap): trim the previous or next edit to the playhead. */
  trimEditToPlayhead(side: 'previous' | 'next', ripple: boolean) {
    const trim = trimToPlayhead(this.seq, this.playhead, side, this.unlocked(), ripple);
    if (!trim) {
      this.say(`No ${side} edit to trim.`);
      return;
    }
    this.commit((s) => {
      s.clips = trim.clips;
    });
    // After a ripple trim of the previous edit, the kept frame now sits at that edit.
    if (side === 'previous' && ripple) this.playhead = trim.edge;
  }

  /** E: extend the selected clip's nearest edge to the playhead. */
  extendToPlayhead() {
    const c = this.selected.length === 1 ? this.selected[0] : null;
    if (!c || this.isLocked(c)) {
      this.say('Select one clip on an unlocked track to extend.');
      return;
    }
    const next = extendEdge(this.seq, c, this.mediaById.get(c.media), this.playhead);
    if (!next) return;
    this.commit((s) => {
      s.clips = s.clips.map((x) => (x.id === c.id ? next : x));
    });
  }

  /** J/K/L: change the shuttle rate and return it; the focused viewer's player starts or stops to match. */
  shuttleKey(key: 'j' | 'k' | 'l'): number {
    this.shuttle = nextShuttleRate(this.shuttle, key);
    return this.shuttle;
  }

  stopShuttle() {
    this.shuttle = 0;
  }

  // ------------------------------------------------------------------ subclips and markers
  subclipsFor(mediaId: string): Subclip[] {
    return this.seq.subclips.filter((x) => x.media === mediaId);
  }

  /** Cmd/Ctrl+U: save the source In-to-Out as a named subclip. */
  makeSubclip(name = '') {
    const src = this.source;
    const m = this.sourceMedia;
    if (!src || !m) {
      this.say('Open a clip in the source viewer first.', true);
      return;
    }
    const a = src.in ?? 0;
    const b = src.out ?? (m.kind === 'image' ? IMAGE_SECONDS : (m.duration ?? 0));
    if (b - a < frame(this.seq) / 2) {
      this.say('Set a source In and Out further apart.', true);
      return;
    }
    if (this.seq.subclips.length >= MAX_SUBCLIPS) {
      this.say(`A sequence can hold up to ${MAX_SUBCLIPS} subclips.`, true);
      return;
    }
    const count = this.subclipsFor(m.id).length + 1;
    const stem = m.name.replace(/\.[^.]+$/, '');
    const sub: Subclip = {
      id: uid('s'),
      media: m.id,
      source_in: a,
      source_out: b,
      name: (name.trim() || `${stem} (${count})`).slice(0, 60),
      color: 'blue',
    };
    this.commit((s) => {
      s.subclips.push(sub);
    });
    src.subclip = sub.id;
    this.say(`Subclip "${sub.name}" saved.`);
  }

  renameSubclip(id: string, name: string) {
    const clean = name.trim().slice(0, 60);
    if (!clean) return;
    this.commit((s) => {
      const sub = s.subclips.find((x) => x.id === id);
      if (sub) sub.name = clean;
    });
  }

  removeSubclip(id: string) {
    this.commit((s) => {
      s.subclips = s.subclips.filter((x) => x.id !== id);
    });
    if (this.source?.subclip === id) this.source.subclip = null;
  }

  /** M: a marker in whichever viewer has focus. */
  markHere() {
    if (this.viewer === 'source' && this.source) {
      const t = this.source.playhead;
      if (!this.source.markers.some((x) => Math.abs(x - t) < 1e-3))
        this.source.markers = [...this.source.markers, t].sort((a, b) => a - b);
      return;
    }
    this.addMarker(this.playhead);
  }

  updateMarker(index: number, change: { label?: string; color?: MarkerColor }) {
    if (!this.seq.markers[index]) return;
    this.commit((s) => {
      const m = s.markers[index];
      if (change.label !== undefined) m.label = change.label.slice(0, 60);
      if (change.color) m.color = change.color;
    });
  }

  removeMarker(index: number) {
    if (!this.seq.markers[index]) return;
    this.commit((s) => {
      s.markers.splice(index, 1);
    });
  }

  // ------------------------------------------------------------------ analysis
  analysisFor(mediaId: string, kind: AnalysisKind): Analysis | null {
    return this.analyses[`${mediaId}:${kind}`] ?? null;
  }

  /** Start (or reuse) an analysis and keep its status fresh until it finishes. */
  async analyse(m: Media, kind: AnalysisKind, params: api.AnalysisParams = {}) {
    const key = `${m.id}:${kind}`;
    if (this.analyses[key]?.status === 'running') return;
    try {
      this.follow(key, await api.startAnalysis(m.id, kind, params));
    } catch (error) {
      // Keep the refusal (e.g. busy processing another file) beside the button that was pressed.
      const message = error instanceof Error ? error.message : 'The analysis could not start.';
      this.analyses = {
        ...this.analyses,
        [key]: { id: '', media: m.id, kind, status: 'error', progress: 0, error: message, created: 0, result: null },
      };
      this.fail(error);
    }
  }

  private follow(key: string, job: Analysis) {
    this.analyses = { ...this.analyses, [key]: job };
    clearTimeout(this.analysisTimers.get(key));
    if (job.status !== 'running') {
      this.analysisTimers.delete(key);
      if (job.status === 'error') this.say(job.error ?? 'The analysis failed.', true);
      return;
    }
    this.analysisTimers.set(
      key,
      setTimeout(async () => {
        try {
          this.follow(key, await api.analysisStatus(job.media, job.id));
        } catch (error) {
          this.analysisTimers.delete(key);
          this.analyses = { ...this.analyses, [key]: { ...job, status: 'error', error: String(error) } };
          this.fail(error);
        }
      }, ANALYSIS_POLL_MS),
    );
  }

  async cancelAnalysis(mediaId: string, kind: AnalysisKind) {
    const job = this.analysisFor(mediaId, kind);
    if (!job || job.status !== 'running') return;
    try {
      await api.cancelAnalysis(mediaId, job.id);
    } catch (error) {
      this.fail(error);
    }
  }

  /** The clips an analysis of this media applies to: selected ones of it, else all of it, unlocked. */
  clipsOf(mediaId: string): Clip[] {
    const mine = (c: Clip) => c.media === mediaId && !this.isLocked(c);
    const chosen = this.selected.filter(mine);
    return chosen.length ? chosen : this.seq.clips.filter(mine);
  }

  /** Timeline spans the given silences would remove from the clips of this media. */
  silenceSpans(mediaId: string, silences: [number, number][], padding: number, least: number): SilenceCut[] {
    const open = this.seq.clips.filter((c) => c.media === mediaId && !this.isLocked(c));
    return silenceCuts(linkedClips(open, this.clipsOf(mediaId)), silences, padding, least);
  }

  /**
   * Ripple-delete the chosen silent spans as one undo step. The cut is made on the clip's own track and
   * on tracks holding other clips of the same media (its detached sound), so picture and sound stay in sync.
   */
  removeSilences(spans: SilenceCut[]) {
    if (!spans.length) {
      this.say('No silences chosen.');
      return;
    }
    const unlocked = this.unlocked();
    const before = this.duration;
    // Latest first, so each cut's times are still right when it is made; like ripple delete, a cut
    // closes up only its own tracks.
    this.commit((s) => {
      for (const [a, b, tracks] of [...spans].sort((x, y) => y[0] - x[0]))
        s.clips = extractRange(s, a, b, new Set(tracks.filter((id) => unlocked.has(id))));
    });
    this.selection = [];
    this.say(
      `Removed ${spans.length} silence${spans.length === 1 ? '' : 's'} (${(before - this.duration).toFixed(1)} s).`,
    );
  }

  /** Scene changes (source times) as timeline times, through every clip of this media that shows them. */
  sceneTimes(mediaId: string, times: number[]): number[] {
    const out = new Set<number>();
    for (const c of this.clipsOf(mediaId))
      for (const t of times) {
        const at = sourceToTimeline(c, t);
        if (at !== null && at > c.start + 1e-6 && at < clipEnd(c) - 1e-6) out.add(toFrame(this.seq, at));
      }
    return [...out].sort((a, b) => a - b);
  }

  scenesToMarkers(mediaId: string, times: number[]) {
    const at = this.sceneTimes(mediaId, times).filter(
      (t) => !this.seq.markers.some((m) => Math.abs(m.time - t) < 1e-6),
    );
    const room = MAX_MARKERS - this.seq.markers.length;
    if (!at.length || room <= 0) {
      this.say(
        room <= 0 ? `A sequence can hold up to ${MAX_MARKERS} markers.` : 'No new scene changes on the timeline.',
      );
      return;
    }
    this.commit((s) => {
      for (const t of at.slice(0, room)) s.markers.push({ time: t, label: 'Scene', color: 'purple' });
      s.markers.sort((a, b) => a.time - b.time);
    });
    this.say(`Added ${Math.min(room, at.length)} scene markers.`);
  }

  scenesToSplits(mediaId: string, times: number[]) {
    const at = this.sceneTimes(mediaId, times);
    if (!at.length) {
      this.say('No scene changes inside clips of that media.');
      return;
    }
    const ids = new Set(this.clipsOf(mediaId).map((c) => c.id));
    this.commit((s) => {
      for (const t of at) {
        const c = s.clips.find((x) => ids.has(x.id) && x.start < t && clipEnd(x) > t);
        const parts = c && splitClip(s, c, t);
        if (!c || !parts) continue;
        ids.add(parts[1].id);
        s.clips = s.clips.flatMap((x) => (x.id === c.id ? parts : [x]));
      }
    });
    this.say(`Split at ${at.length} scene changes.`);
  }

  /** A moment: open it in the source viewer with its marks, or add it to the end of the sequence. */
  openMoment(m: Media, start: number, end: number) {
    this.loadSource(m);
    if (!this.source) return;
    this.source.in = start;
    this.source.out = end;
    this.source.playhead = start;
  }

  appendMoment(m: Media, start: number, end: number) {
    this.openMoment(m, start, end);
    if (this.source) this.sourceEdit('append');
  }

  // ------------------------------------------------------------------ reframing
  /** Live reframe during a drag (inside a gesture): fill the frame and move or scale the picture. */
  reframe(id: string, change: { x?: number; y?: number; scale?: number }) {
    const c = this.seq.clips.find((x) => x.id === id);
    if (!c || this.isLocked(c)) return;
    c.fit = 'fill';
    if (change.x !== undefined) c.x = clamp(change.x, -1, 1);
    if (change.y !== undefined) c.y = clamp(change.y, -1, 1);
    if (change.scale !== undefined) c.scale = clamp(change.scale, 0.1, 4);
  }
}
