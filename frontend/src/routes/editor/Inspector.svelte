<script lang="ts">
  import type { Editor } from '#lib/editor/editor.svelte.ts';
  import {
    adjacentBefore,
    clamp,
    clipDuration,
    FORMATS,
    RATES,
    settle,
    timecode,
    transitionHalf,
  } from '#lib/editor/timeline.ts';
  import type { Clip, Track } from '#lib/editor/types.ts';

  let { editor }: { editor: Editor } = $props();

  const SPEEDS = [0.25, 0.5, 0.75, 1, 1.25, 1.5, 2, 3, 4];
  const LOUDNESS = [
    { value: '', label: 'Off (keep levels)' },
    { value: '-14', label: '-14 LUFS: YouTube, streaming, social' },
    { value: '-16', label: '-16 LUFS: podcasts' },
    { value: '-23', label: '-23 LUFS: broadcast (EBU R128)' },
  ];

  const seq = $derived(editor.seq);
  const clip = $derived(editor.selected.length === 1 ? editor.selected[0] : null);
  const media = $derived(clip ? editor.mediaById.get(clip.media) : undefined);
  const track = $derived(editor.selectedTrack ? seq.tracks.find((t) => t.id === editor.selectedTrack) : undefined);
  const previous = $derived(clip ? adjacentBefore(seq, clip) : null);
  const format = $derived(FORMATS.findIndex((f) => f.width === seq.width && f.height === seq.height).toString());
  const usable = $derived.by(() => {
    if (!clip?.transition || !previous) return 0;
    return 2 * transitionHalf(previous, editor.mediaById.get(previous.media), clip, media, seq.fps);
  });
  const locked = $derived(clip ? editor.isLocked(clip) : false);

  let sliding = false;

  function value(e: Event): number | null {
    const v = (e.currentTarget as HTMLInputElement).valueAsNumber;
    return Number.isFinite(v) ? v : null;
  }

  /** One undoable change to the selected clip; resettle when its length or place changed. */
  function edit(change: (c: Clip) => void, resettle = false) {
    const id = clip?.id;
    if (!id || locked) return;
    editor.commit((s) => {
      const c = s.clips.find((x) => x.id === id);
      if (!c) return;
      change(c);
      if (resettle) s.clips = settle(s, [id]);
    });
  }

  /** Sliders update live and record a single undo step when released. */
  function slide(e: Event, apply: (v: number) => void) {
    const v = value(e);
    if (v === null || locked) return;
    if (!sliding) {
      editor.beginGesture();
      sliding = true;
    }
    apply(v);
  }

  function slid() {
    if (!sliding) return;
    sliding = false;
    editor.endGesture();
  }

  function setStart(e: Event) {
    const v = value(e);
    if (v !== null) edit((c) => (c.start = Math.max(0, v)), true);
  }

  function setIn(e: Event) {
    const v = value(e);
    if (v === null || !clip) return;
    const latest = clip.source_out - clip.speed / seq.fps;
    edit((c) => (c.source_in = clamp(v, 0, latest)), true);
  }

  function setOut(e: Event) {
    const v = value(e);
    if (v === null || !clip) return;
    const longest = media?.kind === 'image' ? 4 * 3600 : (media?.duration ?? v);
    edit((c) => (c.source_out = clamp(v, c.source_in + c.speed / seq.fps, longest)), true);
  }

  function setSpeed(e: Event) {
    const v = Number((e.currentTarget as HTMLSelectElement).value);
    if (Number.isFinite(v)) edit((c) => (c.speed = clamp(v, 0.25, 4)), true);
  }

  function setFade(e: Event, key: 'fade_in' | 'fade_out') {
    const v = value(e);
    if (v !== null && clip) edit((c) => (c[key] = clamp(v, 0, Math.min(10, clipDuration(c)))));
  }

  function setTransition(e: Event) {
    const on = (e.currentTarget as HTMLSelectElement).value === 'dissolve';
    edit((c) => (c.transition = on ? { kind: 'dissolve', duration: 1 } : null));
  }

  function resetPicture() {
    edit((c) => Object.assign(c, { fit: 'fit', scale: 1, x: 0, y: 0, opacity: 1 }));
  }

  function setTrack(t: Track, change: (t: Track) => void) {
    editor.commit(() => change(t));
  }

  function setFormat(e: Event) {
    const f = FORMATS[Number((e.currentTarget as HTMLSelectElement).value)];
    if (f)
      editor.commit((s) => {
        s.width = f.width;
        s.height = f.height;
      });
  }

  function confirmRemoveSequence() {
    if (confirm(`Delete the sequence "${seq.name}"? Media stays in the bin.`))
      void editor.remove().catch((error: unknown) => editor.fail(error));
  }
</script>

<aside class="inspector" aria-labelledby="inspector-title">
  {#if clip && media !== undefined}
    <h2 id="inspector-title">Clip</h2>
    <p class="title" title={media.name}>{media.name}</p>
    {#if locked}<p class="hint">This clip's track is locked.</p>{/if}

    <fieldset disabled={locked}>
      <legend>Timing</legend>
      <div class="pair">
        <label
          >Start (s)<input
            type="number"
            min="0"
            step={1 / seq.fps}
            value={clip.start.toFixed(3)}
            onchange={setStart}
          /></label
        >
        <label>Length<output>{clipDuration(clip).toFixed(2)} s</output></label>
      </div>
      {#if media.kind !== 'image'}
        <div class="pair">
          <label
            >Source in (s)<input
              type="number"
              min="0"
              step={1 / seq.fps}
              value={clip.source_in.toFixed(3)}
              onchange={setIn}
            /></label
          >
          <label
            >Source out (s)<input
              type="number"
              min="0"
              step={1 / seq.fps}
              value={clip.source_out.toFixed(3)}
              onchange={setOut}
            /></label
          >
        </div>
        <label
          >Speed
          <select value={String(clip.speed)} onchange={setSpeed}>
            {#each SPEEDS as s (s)}<option value={String(s)}>{s}×</option>{/each}
          </select>
        </label>
      {:else}
        <label
          >Duration (s)<input
            type="number"
            min={1 / seq.fps}
            max="14400"
            step="0.5"
            value={clip.source_out.toFixed(2)}
            onchange={setOut}
          /></label
        >
      {/if}
    </fieldset>

    {#if media.has_audio}
      <fieldset disabled={locked}>
        <legend>Sound</legend>
        <label class="slider"
          >Volume <span>{clip.volume > 0 ? '+' : ''}{clip.volume.toFixed(1)} dB</span>
          <input
            type="range"
            min="-60"
            max="12"
            step="0.5"
            value={clip.volume}
            oninput={(e) => slide(e, (v) => clip && (clip.volume = v))}
            onchange={slid}
          />
        </label>
        <label class="check"
          ><input type="checkbox" checked={clip.muted} onchange={() => edit((c) => (c.muted = !c.muted))} />Mute clip</label
        >
      </fieldset>
    {/if}

    <fieldset disabled={locked}>
      <legend>Fades</legend>
      <div class="pair">
        <label
          >Fade in (s)<input
            type="number"
            min="0"
            max="10"
            step="0.1"
            value={clip.fade_in}
            onchange={(e) => setFade(e, 'fade_in')}
          /></label
        >
        <label
          >Fade out (s)<input
            type="number"
            min="0"
            max="10"
            step="0.1"
            value={clip.fade_out}
            onchange={(e) => setFade(e, 'fade_out')}
          /></label
        >
      </div>
      {#if previous}
        <label
          >Transition from previous clip
          <select value={clip.transition ? 'dissolve' : ''} onchange={setTransition}>
            <option value="">Cut</option>
            <option value="dissolve">Cross dissolve</option>
          </select>
        </label>
        {#if clip.transition}
          <label
            >Dissolve length (s)<input
              type="number"
              min="0.04"
              max="5"
              step="0.1"
              value={clip.transition.duration}
              onchange={(e) => {
                const v = value(e);
                if (v !== null) edit((c) => c.transition && (c.transition.duration = clamp(v, 0.04, 5)));
              }}
            /></label
          >
          <p class="hint">
            {#if usable === 0}
              No spare media around this cut, so it stays a cut. Trim the clips shorter first.
            {:else if usable < clip.transition.duration - 1e-3}
              Shortened to {usable.toFixed(2)} s by the media available around the cut.
            {:else}
              Centred on the cut.
            {/if}
          </p>
        {/if}
      {/if}
    </fieldset>

    {#if media.kind !== 'audio'}
      <fieldset disabled={locked}>
        <legend>Picture</legend>
        <label
          >Frame
          <select
            value={clip.fit}
            onchange={(e) => {
              const fit = (e.currentTarget as HTMLSelectElement).value === 'fill' ? 'fill' : 'fit';
              edit((c) => (c.fit = fit));
            }}
          >
            <option value="fit">Fit (show the whole picture)</option>
            <option value="fill">Fill (crop to the frame)</option>
          </select>
        </label>
        <label class="slider"
          >Scale <span>{Math.round(clip.scale * 100)}%</span>
          <input
            type="range"
            min="10"
            max="500"
            step="1"
            value={Math.round(clip.scale * 100)}
            oninput={(e) => slide(e, (v) => clip && (clip.scale = v / 100))}
            onchange={slid}
          />
        </label>
        <label class="slider"
          >Position X <span>{Math.round(clip.x * 100)}%</span>
          <input
            type="range"
            min="-100"
            max="100"
            step="1"
            value={Math.round(clip.x * 100)}
            oninput={(e) => slide(e, (v) => clip && (clip.x = v / 100))}
            onchange={slid}
          />
        </label>
        <label class="slider"
          >Position Y <span>{Math.round(clip.y * 100)}%</span>
          <input
            type="range"
            min="-100"
            max="100"
            step="1"
            value={Math.round(clip.y * 100)}
            oninput={(e) => slide(e, (v) => clip && (clip.y = v / 100))}
            onchange={slid}
          />
        </label>
        <label class="slider"
          >Opacity <span>{Math.round(clip.opacity * 100)}%</span>
          <input
            type="range"
            min="0"
            max="100"
            step="1"
            value={Math.round(clip.opacity * 100)}
            oninput={(e) => slide(e, (v) => clip && (clip.opacity = v / 100))}
            onchange={slid}
          />
        </label>
        <button type="button" class="btn secondary small" onclick={resetPicture}>Reset picture</button>
      </fieldset>
    {/if}

    <div class="actions">
      <button type="button" class="btn secondary small" onclick={() => editor.splitAt(editor.playhead, [clip])}
        >Split at playhead</button
      >
      {#if media.kind === 'video' && media.has_audio && !clip.muted}
        <button type="button" class="btn secondary small" onclick={() => clip && editor.detachAudio(clip)}
          >Detach audio</button
        >
      {/if}
      <button type="button" class="btn danger small" onclick={() => editor.deleteSelected(false)}>Delete</button>
    </div>
  {:else if editor.selected.length > 1}
    <h2 id="inspector-title">{editor.selected.length} clips</h2>
    <p class="hint">Drag any of them to move them together, or use the timeline tools.</p>
    <div class="actions">
      <button type="button" class="btn secondary small" onclick={() => editor.splitAt(editor.playhead)}
        >Split at playhead</button
      >
      <button type="button" class="btn secondary small" onclick={() => editor.addDissolve()}>Add dissolves</button>
      <button type="button" class="btn danger small" onclick={() => editor.deleteSelected(false)}>Delete</button>
      <button type="button" class="btn danger small" onclick={() => editor.deleteSelected(true)}>Ripple delete</button>
    </div>
  {:else if track}
    <h2 id="inspector-title">Track</h2>
    <label
      >Name<input
        type="text"
        maxlength="40"
        value={track.name}
        onchange={(e) => {
          const name = (e.currentTarget as HTMLInputElement).value.trim().slice(0, 40);
          if (name && track) setTrack(track, (t) => (t.name = name));
        }}
      /></label
    >
    <label class="slider"
      >Track volume <span>{track.volume > 0 ? '+' : ''}{track.volume.toFixed(1)} dB</span>
      <input
        type="range"
        min="-60"
        max="12"
        step="0.5"
        value={track.volume}
        oninput={(e) => slide(e, (v) => track && (track.volume = v))}
        onchange={slid}
      />
    </label>
    {#if track.kind === 'audio'}
      <label class="check"
        ><input
          type="checkbox"
          checked={track.duck}
          onchange={() => track && setTrack(track, (t) => (t.duck = !t.duck))}
        />Duck under speech</label
      >
      <p class="hint">
        Lowers this track by {seq.duck_db} dB whenever another track has sound. Use it for music beds. The export follows
        the speech level; the preview lowers it while other clips play.
      </p>
    {/if}
    <button type="button" class="btn danger small" onclick={() => track && editor.removeTrack(track.id)}
      >Remove track</button
    >
  {:else}
    <h2 id="inspector-title">Sequence</h2>
    <label
      >Name<input
        type="text"
        maxlength="80"
        value={seq.name}
        onchange={(e) => {
          const name = (e.currentTarget as HTMLInputElement).value.trim().slice(0, 80);
          if (name) editor.commit((s) => (s.name = name));
        }}
      /></label
    >
    <label
      >Format
      <select value={format} onchange={setFormat}>
        {#if format === '-1'}<option value="-1">{seq.width} × {seq.height}</option>{/if}
        {#each FORMATS as f, i (f.label)}<option value={String(i)}>{f.label}</option>{/each}
      </select>
    </label>
    <label
      >Frame rate
      <select
        value={String(seq.fps)}
        onchange={(e) => {
          const fps = Number((e.currentTarget as HTMLSelectElement).value);
          editor.commit((s) => (s.fps = fps));
        }}
      >
        {#each RATES as r (r)}<option value={String(r)}>{r} fps</option>{/each}
      </select>
    </label>
    <label class="slider"
      >Music ducking <span>{seq.duck_db} dB</span>
      <input
        type="range"
        min="0"
        max="30"
        step="1"
        value={seq.duck_db}
        oninput={(e) => slide(e, (v) => (seq.duck_db = v))}
        onchange={slid}
      />
    </label>
    <label
      >Loudness on export
      <select
        value={seq.loudness === null ? '' : String(seq.loudness)}
        onchange={(e) => {
          const v = (e.currentTarget as HTMLSelectElement).value;
          editor.commit((s) => (s.loudness = v ? Number(v) : null));
        }}
      >
        {#each LOUDNESS as l (l.value)}<option value={l.value}>{l.label}</option>{/each}
      </select>
    </label>
    <p class="hint">Exports also pass through a limiter, so peaks never clip.</p>

    <h3>In and out</h3>
    {#if seq.range_in !== null || seq.range_out !== null}
      <p class="range">
        {timecode(seq.range_in ?? 0, seq.fps)} to {timecode(seq.range_out ?? editor.duration, seq.fps)}
        <button type="button" class="link" onclick={() => editor.clearInOut()}>Clear</button>
      </p>
    {:else}
      <p class="hint">Press I and O at the playhead to mark a clip to export.</p>
    {/if}

    <h3>Markers</h3>
    {#if seq.markers.length}
      <ul class="markers">
        {#each seq.markers as m, i (m.time)}
          <li>
            <button type="button" class="link" onclick={() => (editor.playhead = m.time)}
              >{timecode(m.time, seq.fps)}</button
            >
            <input
              type="text"
              maxlength="60"
              aria-label="Marker label"
              value={m.label}
              onchange={(e) => {
                const label = (e.currentTarget as HTMLInputElement).value.slice(0, 60);
                editor.commit((s) => (s.markers[i].label = label));
              }}
            />
            <button
              type="button"
              class="mini"
              aria-label="Delete marker at {timecode(m.time, seq.fps)}"
              onclick={() => editor.commit((s) => s.markers.splice(i, 1))}>×</button
            >
          </li>
        {/each}
      </ul>
    {:else}
      <p class="hint">Press M to drop a marker at the playhead.</p>
    {/if}

    <details>
      <summary>Keyboard shortcuts</summary>
      <dl class="keys">
        <dt>Space</dt>
        <dd>Play or pause</dd>
        <dt>← →</dt>
        <dd>One frame (Shift: one second)</dd>
        <dt>↑ ↓</dt>
        <dd>Previous or next edit point</dd>
        <dt>Home End</dt>
        <dd>Start or end</dd>
        <dt>V, C</dt>
        <dd>Selection or razor tool</dd>
        <dt>Ctrl/⌘ K, Ctrl/⌘ B</dt>
        <dd>Split at playhead</dd>
        <dt>Delete</dt>
        <dd>Delete selected clips</dd>
        <dt>Shift Delete</dt>
        <dd>Ripple delete</dd>
        <dt>Ctrl/⌘ D</dt>
        <dd>Cross dissolve</dd>
        <dt>Alt ← →</dt>
        <dd>Nudge a focused clip one frame</dd>
        <dt>M, I, O</dt>
        <dd>Marker, mark in, mark out</dd>
        <dt>S</dt>
        <dd>Snapping on or off</dd>
        <dt>= - \</dt>
        <dd>Zoom in, out, to fit</dd>
        <dt>Ctrl/⌘ Z</dt>
        <dd>Undo (Shift to redo)</dd>
      </dl>
    </details>
    <button type="button" class="btn danger small" disabled={!editor.seqId} onclick={confirmRemoveSequence}
      >Delete sequence</button
    >
  {/if}
</aside>

<style>
  .inspector {
    display: flex;
    flex-direction: column;
    gap: 10px;
    min-height: 0;
    overflow-y: auto;
    padding: 10px 14px 16px;
    background: var(--card);
    border-left: 1px solid var(--line);
    font-size: 0.88rem;
  }
  h2 {
    margin: 0;
    font-size: 0.95rem;
  }
  h3 {
    margin: 6px 0 0;
    font-size: 0.85rem;
  }
  .title {
    margin: -6px 0 0;
    font-weight: 600;
    color: var(--muted);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  fieldset {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin: 0;
    padding: 10px 0 0;
    border: 0;
    border-top: 1px solid var(--line);
    min-width: 0;
  }
  legend {
    font-weight: 700;
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--muted);
    padding: 0;
    float: left;
    width: 100%;
    margin-bottom: 2px;
  }
  label {
    display: flex;
    flex-direction: column;
    gap: 3px;
    font-weight: 600;
    font-size: 0.82rem;
    min-width: 0;
  }
  label.slider span {
    position: absolute;
    right: 0;
    font-weight: 500;
    color: var(--muted);
    font-variant-numeric: tabular-nums;
  }
  label.slider {
    position: relative;
  }
  label.check {
    flex-direction: row;
    align-items: center;
    gap: 6px;
    font-weight: 500;
  }
  .pair {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  }
  input[type='number'],
  input[type='text'],
  select {
    width: 100%;
    padding: 5px 8px;
    font-size: 0.85rem;
  }
  output {
    padding: 5px 0;
    font-weight: 500;
    font-variant-numeric: tabular-nums;
  }
  .hint {
    margin: 0;
    font-size: 0.8rem;
  }
  .actions {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    padding-top: 10px;
    border-top: 1px solid var(--line);
  }
  .small {
    padding: 5px 10px;
    font-size: 0.82rem;
  }
  .range {
    margin: 0;
    font-variant-numeric: tabular-nums;
  }
  .link {
    font: inherit;
    color: var(--accent);
    background: none;
    border: 0;
    padding: 0 4px;
    cursor: pointer;
    font-weight: 600;
    text-decoration: underline;
  }
  .markers {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .markers li {
    display: grid;
    grid-template-columns: auto 1fr auto;
    gap: 4px;
    align-items: center;
    font-variant-numeric: tabular-nums;
  }
  .mini {
    width: 24px;
    height: 24px;
    padding: 0;
    font: inherit;
    font-weight: 700;
    color: var(--ink);
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 5px;
    cursor: pointer;
  }
  details summary {
    cursor: pointer;
    font-weight: 600;
  }
  .keys {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 3px 10px;
    margin: 8px 0 0;
    font-size: 0.8rem;
  }
  .keys dt {
    font-weight: 600;
    white-space: nowrap;
  }
  .keys dd {
    margin: 0;
    color: var(--muted);
  }
</style>
