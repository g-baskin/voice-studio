<script lang="ts">
  import { onMount } from 'svelte';
  import type { Editor } from '#lib/editor/editor.svelte.ts';
  import { Player } from '#lib/editor/player.ts';
  import { editPoints, timecode, toFrame } from '#lib/editor/timeline.ts';

  let { editor }: { editor: Editor } = $props();

  let canvas: HTMLCanvasElement | undefined = $state();
  let raf = 0;
  let pending = 0;
  let from = 0;
  let startedAt = 0;
  let written = 0;

  const player = new Player(() => {
    // Seeks finish asynchronously; coalesce their redraws into one frame.
    if (editor.playing || pending) return;
    pending = requestAnimationFrame(() => {
      pending = 0;
      if (!editor.playing) player.update(editor.seq, editor.layers, editor.playhead, false);
    });
  });

  $effect(() => {
    if (canvas) player.attach(canvas);
  });

  // Browser-only teardown; the page is prerendered, where these APIs do not exist.
  onMount(() => () => {
    cancelAnimationFrame(raf);
    cancelAnimationFrame(pending);
    player.destroy();
  });

  // Paused: redraw whenever the playhead or the edit changes.
  $effect(() => {
    const t = editor.playhead;
    const layers = editor.layers;
    if (!editor.playing) player.update(editor.seq, layers, t, false);
  });

  function tick(now: number) {
    if (!editor.playing) return;
    if (Math.abs(editor.playhead - written) > 1e-3) {
      // Someone scrubbed while playing: continue from there.
      from = editor.playhead;
      startedAt = now;
    }
    const t = from + (now - startedAt) / 1000;
    const end = editor.duration;
    if (t >= end) {
      editor.playhead = end;
      pause();
      return;
    }
    editor.playhead = written = t;
    player.update(editor.seq, editor.layers, t, true);
    raf = requestAnimationFrame(tick);
  }

  export function play() {
    if (editor.playing || !editor.duration) return;
    player.unlock();
    if (editor.playhead >= editor.duration - 1 / editor.seq.fps) editor.playhead = 0;
    from = written = editor.playhead;
    startedAt = performance.now();
    editor.playing = true;
    raf = requestAnimationFrame(tick);
  }

  export function pause() {
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

<section class="monitor" aria-label="Program monitor">
  <div class="stage">
    <canvas bind:this={canvas} aria-label="Preview of the sequence at {timecode(editor.playhead, editor.seq.fps)}"
    ></canvas>
    {#if !editor.seq.clips.length}
      <p class="hint empty">Import media and drag it onto the timeline to start editing.</p>
    {/if}
  </div>
  <div class="transport">
    <span class="tc" aria-label="Playhead time">{timecode(editor.playhead, editor.seq.fps)}</span>
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
  .monitor {
    display: flex;
    flex-direction: column;
    min-width: 0;
    min-height: 0;
    background: var(--bg);
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
