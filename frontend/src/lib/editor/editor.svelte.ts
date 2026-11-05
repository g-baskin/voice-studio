import * as api from './api.ts';
import {
  clipEnd,
  clipFor,
  newSequence,
  plan,
  rippleDelete,
  seqDuration,
  settle,
  splitClip,
  toFrame,
  track,
  trackKindFor,
  uid,
} from './timeline.ts';
import type { Clip, Media, Sequence, SequenceSummary, TrackKind } from './types.ts';

const HISTORY = 100;
const SAVE_DELAY = 700;
const POLL_MS = 1000;

export type SaveState = 'saved' | 'saving' | 'unsaved' | 'error';
export type Tool = 'select' | 'razor';

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

  mediaById = $derived(new Map(this.media.map((m) => [m.id, m])));
  layers = $derived(plan(this.seq, this.mediaById));
  duration = $derived(seqDuration(this.seq));
  selected = $derived(this.seq.clips.filter((c) => this.selection.includes(c.id)));

  private past: Sequence[] = [];
  private future: Sequence[] = [];
  private gestureBase: Sequence | null = null;
  private saveTimer: ReturnType<typeof setTimeout> | undefined;
  private pollTimer: ReturnType<typeof setTimeout> | undefined;
  private saving: Promise<void> | null = null;
  private peaks = new Map<string, Uint8Array | null>();
  private thumbs = new Map<string, HTMLImageElement>();

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
    this.remember(base);
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
      s.markers.push({ time: at, label: `Marker ${s.markers.length + 1}` });
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
}
