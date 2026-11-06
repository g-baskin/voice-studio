<script lang="ts">
  import { onMount } from 'svelte';
  import type { Editor } from '#lib/editor/editor.svelte.ts';
  import { pageAt, pageText } from '#lib/editor/captions.ts';
  import { Player, type TrimSide } from '#lib/editor/player.ts';
  import { editPoints, FORMATS, timecode, toFrame } from '#lib/editor/timeline.ts';
  import ReframeOverlay from './ReframeOverlay.svelte';

  let { editor, onplay }: { editor: Editor; onplay?: () => void } = $props();

  let canvas: HTMLCanvasElement | undefined = $state();
  let raf = 0;
  let pending = 0;
  let from = 0;
  let startedAt = 0;
  let written = 0;
  let rate = 1;
  let reframing = $state(false);

  // Social shapes offered beside the program viewer in Clip mode: landscape, vertical, square.
  const PRESETS = [
    { ...FORMATS[0], label: '16:9', title: 'Landscape 1920 × 1080' },
    { ...FORMATS[1], label: '9:16', title: 'Vertical 1080 × 1920 for Shorts, Reels, TikTok' },
    { ...FORMATS[2], label: '1:1', title: 'Square 1080 × 1080' },
  ];

  function setFormat(width: number, height: number) {
    if (editor.seq.width === width && editor.seq.height === height) return;
    editor.commit((s) => {
      s.width = width;
      s.height = height;
    });
    editor.say(`Sequence is now ${width} × ${height}.`);
  }

  const player = new Player(() => {
    // Seeks finish asynchronously; coalesce their redraws into one frame.
    if (editor.playing || pending) return;
    pending = requestAnimationFrame(() => {
      pending = 0;
      if (!editor.playing) still();
    });
  });

  const side = (frame: { clip: string; time: number } | null): TrimSide => {
    const layer = frame && editor.layers.find((l) => l.clip.id === frame.clip);
    return layer && frame ? { layer, time: frame.time } : null;
  };

  // Paused frame: the trim view's two frames while trimming, else the playhead's frame.
  function still() {
    const view = editor.trimView;
    if (view) player.trim(editor.seq, side(view.left), side(view.right));
    else player.update(editor.seq, editor.layers, editor.playhead, false);
  }

  $effect(() => {
    if (canvas) player.attach(canvas);
  });

  // Browser-only teardown; the page is prerendered, where these APIs do not exist.
  onMount(() => () => {
    cancelAnimationFrame(raf);
    cancelAnimationFrame(pending);
    player.destroy();
  });

  // Captions are drawn only once their font is ready, so the preview never flashes a fallback face.
  const captionFamily = $derived(editor.seq.captions?.enabled ? editor.fonts[editor.seq.captions.font] : undefined);
  const captionNow = $derived(
    editor.seq.captions?.enabled ? pageText(pageAt(editor.captionPages, editor.playhead)) : '',
  );

  $effect(() => {
    void editor.seq.captions?.enabled;
    void editor.seq.captions?.font;
    void editor.seq.captions?.track;
    void editor.seq.clips;
    editor.prepareCaptions();
  });

  $effect(() => {
    const caps = editor.seq.captions;
    player.captions =
      caps?.enabled && captionFamily ? { caps, pages: editor.captionPages, family: captionFamily } : null;
  });

  // Paused: redraw whenever the playhead, the edit, the captions or the trim view changes.
  $effect(() => {
    void editor.playhead;
    void editor.layers;
    void editor.trimView;
    void editor.captionPages;
    void captionFamily;
    void JSON.stringify(editor.seq.captions);
    if (!editor.playing) still();
  });

  function tick(now: number) {
    if (!editor.playing) return;
    if (Math.abs(editor.playhead - written) > 1e-3) {
      // Someone scrubbed while playing: continue from there.
      from = editor.playhead;
      startedAt = now;
    }
    // A frame's timestamp can predate startedAt; reversing from the very end would then step past it and stop.
    const t = from + (rate * Math.max(0, now - startedAt)) / 1000;
    const end = editor.duration;
    // Stop only at the edge playback is heading for: reversing starts exactly at the end.
    if ((rate > 0 && t >= end) || (rate < 0 && t <= 0)) {
      editor.playhead = Math.min(end, Math.max(0, t));
      pause();
      return;
    }
    editor.playhead = written = t;
    player.update(editor.seq, editor.layers, t, true, rate);
    raf = requestAnimationFrame(tick);
  }

  export function play() {
    if (editor.playing || !editor.duration) return;
    onplay?.();
    if (editor.shuttle <= 0) editor.shuttle = 1;
    start();
  }

  function start() {
    player.unlock();
    rate = editor.shuttle;
    const fps = editor.seq.fps;
    if (rate > 0 && editor.playhead >= editor.duration - 1 / fps) editor.playhead = 0;
    if (rate < 0 && editor.playhead <= 1 / fps) editor.playhead = editor.duration;
    from = written = editor.playhead;
    startedAt = performance.now();
    if (editor.playing) return;
    editor.playing = true;
    raf = requestAnimationFrame(tick);
  }

  /** J/K/L shuttle: J and L step the speed up 1×, 2×, 4×, 8× backwards or forwards; K stops. */
  export function shuttle(key: 'j' | 'k' | 'l') {
    if (!editor.duration) return;
    if (!editor.playing) onplay?.();
    if (editor.shuttleKey(key) === 0) pause();
    else start();
  }

  export function pause() {
    editor.stopShuttle();
    if (!editor.playing) return;
    editor.playing = false;
    cancelAnimationFrame(raf);
    player.stopAll();
    editor.playhead = toFrame(editor.seq, editor.playhead);
  }

  export function toggle() {
    if (editor.playing) pause();
    else play();
  }

  export function step(seconds: number) {
    pause();
    editor.playhead = toFrame(editor.seq, Math.max(0, editor.playhead + seconds));
  }

  export function jumpEdit(direction: 1 | -1) {
    pause();
    const points = editPoints(editor.seq);
    const t = editor.playhead;
    const next = direction > 0 ? points.find((p) => p > t + 1e-3) : points.findLast((p) => p < t - 1e-3);
    if (next !== undefined) editor.playhead = next;
  }

  export function home(end: boolean) {
    pause();
    editor.playhead = end ? editor.duration : 0;
  }
</script>

<section
  class="monitor"
  class:focused={editor.mode === 'clip' && editor.viewer === 'program'}
  aria-label="Program monitor"
  onpointerdowncapture={() => (editor.viewer = 'program')}
  onfocusin={() => (editor.viewer = 'program')}
>
  {#if editor.mode === 'clip'}
    <header>
      <h2>Program</h2>
      <span class="name" title={editor.seq.name}>{editor.seq.name}</span>
      <div class="presets" role="group" aria-label="Sequence shape">
        {#each PRESETS as p (p.label)}
          <button
            type="button"
            aria-pressed={editor.seq.width === p.width && editor.seq.height === p.height}
            title={p.title}
            onclick={() => setFormat(p.width, p.height)}>{p.label}</button
          >
        {/each}
      </div>
      <button
        type="button"
        class="reframe-toggle"
        aria-pressed={reframing}
        title="Show the frame over the program and drag the picture into place (Alt+drag to scale)"
        onclick={() => (reframing = !reframing)}>Reframe</button
      >
    </header>
  {/if}
  <div class="stage">
    <canvas bind:this={canvas} aria-label="Preview of the sequence at {timecode(editor.playhead, editor.seq.fps)}"
    ></canvas>
    <!-- The caption on screen, for screen readers on request (not announced as it changes). -->
    <p id="caption-now" class="visually-hidden" aria-live="off">{captionNow}</p>
    {#if editor.trimView && !editor.playing}
      <div class="trim-labels" aria-live="polite">
        <span>Outgoing {editor.trimView.left ? timecode(editor.trimView.left.time, editor.seq.fps) : '—'}</span>
        <span>Incoming {editor.trimView.right ? timecode(editor.trimView.right.time, editor.seq.fps) : '—'}</span>
      </div>
    {/if}
    {#if reframing && editor.mode === 'clip' && !editor.playing && !editor.trimView}
      <ReframeOverlay {editor} {canvas} />
    {/if}
    {#if !editor.seq.clips.length}
      <p class="hint empty">Import media and drag it onto the timeline to start editing.</p>
    {/if}
  </div>
  <div class="transport">
    <span class="tc" aria-label="Playhead time">
      {timecode(editor.playhead, editor.seq.fps)}
      {#if editor.playing && editor.shuttle !== 1}
        <span class="rate" aria-label="Shuttle speed">{editor.shuttle < 0 ? '◀' : '▶'} {Math.abs(editor.shuttle)}×</span
        >
      {/if}
    </span>
    <div class="buttons">
      <button type="button" aria-label="Go to start" title="Go to start (Home)" onclick={() => home(false)}>
        <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 3v10M13 3L6 8l7 5z" /></svg>
      </button>
      <button type="button" aria-label="Previous edit" title="Previous edit point (Up)" onclick={() => jumpEdit(-1)}>
        <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 3L2 8l6 5zM14 3L8 8l6 5z" /></svg>
      </button>
      <button
        type="button"
        aria-label="Back one frame"
        title="Back one frame (Left)"
        onclick={() => step(-1 / editor.seq.fps)}
      >
        <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M11 3L5 8l6 5z" /></svg>
      </button>
      <button
        type="button"
        class="play"
        aria-label={editor.playing ? 'Pause' : 'Play'}
        title="Play or pause (Space)"
        onclick={toggle}
      >
        {#if editor.playing}
          <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M5 3v10M11 3v10" /></svg>
        {:else}
          <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M5 3l8 5-8 5z" /></svg>
        {/if}
      </button>
      <button
        type="button"
        aria-label="Forward one frame"
        title="Forward one frame (Right)"
        onclick={() => step(1 / editor.seq.fps)}
      >
        <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M5 3l6 5-6 5z" /></svg>
      </button>
      <button type="button" aria-label="Next edit" title="Next edit point (Down)" onclick={() => jumpEdit(1)}>
        <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 3l6 5-6 5zM2 3l6 5-6 5z" /></svg>
      </button>
      <button type="button" aria-label="Go to end" title="Go to end (End)" onclick={() => home(true)}>
        <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M13 3v10M3 3l7 5-7 5z" /></svg>
      </button>
    </div>
    <span class="tc muted" aria-label="Sequence length">{timecode(editor.duration, editor.seq.fps)}</span>
  </div>
</section>

<style>
  .visually-hidden {
    position: absolute;
    width: 1px;
    height: 1px;
    margin: -1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
  }
  .monitor {
    display: flex;
    flex-direction: column;
    min-width: 0;
    min-height: 0;
    background: var(--bg);
  }
  .monitor.focused {
    box-shadow: inset 0 2px 0 var(--accent);
  }
  header {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 10px;
    min-width: 0;
  }
  h2 {
    margin: 0;
    font-size: 0.85rem;
  }
  .name {
    flex: 1;
    min-width: 0;
    font-size: 0.8rem;
    color: var(--muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .presets {
    display: flex;
    gap: 2px;
  }
  header button {
    min-width: 26px;
    height: 24px;
    padding: 0 6px;
    font: inherit;
    font-size: 0.78rem;
    font-weight: 700;
    color: var(--ink);
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 5px;
    cursor: pointer;
  }
  header button[aria-pressed='true'] {
    color: var(--accent-ink);
    background: var(--accent);
    border-color: var(--accent);
  }
  .stage {
    position: relative;
    flex: 1;
    min-height: 0;
    padding: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  canvas {
    display: block;
    width: 100%;
    height: 100%;
    /* The drawn frame keeps the sequence's shape at any panel size. */
    object-fit: contain;
  }
  .empty {
    position: absolute;
    color: #c9d1cc;
    text-align: center;
    max-width: 22em;
    margin: 0;
  }
  .trim-labels {
    position: absolute;
    left: 12px;
    right: 12px;
    bottom: 12px;
    display: grid;
    grid-template-columns: 1fr 1fr;
    text-align: center;
    font-size: 0.8rem;
    font-variant-numeric: tabular-nums;
    pointer-events: none;
  }
  .trim-labels span {
    justify-self: center;
    padding: 2px 8px;
    border-radius: 4px;
    color: #fff;
    background: rgb(0 0 0 / 0.75);
  }
  .rate {
    margin-left: 6px;
    padding: 0 5px;
    border-radius: 4px;
    font-size: 0.75rem;
    color: var(--accent-ink);
    background: var(--accent);
  }
  .transport {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    padding: 6px 12px;
    border-top: 1px solid var(--line);
    background: var(--card);
  }
  .tc {
    font-variant-numeric: tabular-nums;
    font-size: 0.9rem;
    font-weight: 600;
    color: var(--accent);
    min-width: 7.5em;
  }
  .tc.muted {
    color: var(--muted);
    text-align: right;
  }
  .buttons {
    display: flex;
    gap: 2px;
  }
  .buttons button {
    width: 32px;
    height: 30px;
    display: grid;
    place-items: center;
    color: var(--ink);
    background: none;
    border: 1px solid transparent;
    border-radius: 6px;
    cursor: pointer;
    padding: 0;
  }
  .buttons button:hover {
    background: var(--bg);
    border-color: var(--line);
  }
  .buttons .play {
    width: 40px;
    color: var(--accent-ink);
    background: var(--accent);
  }
  .buttons .play:hover {
    background: var(--accent);
  }
  svg {
    width: 15px;
    height: 15px;
    fill: currentColor;
    stroke: currentColor;
    stroke-width: 1.4;
    stroke-linejoin: round;
  }
</style>
