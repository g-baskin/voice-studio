<script lang="ts">
  import { onMount } from 'svelte';
  import { proxyUrl } from '#lib/editor/api.ts';
  import type { Editor } from '#lib/editor/editor.svelte.ts';
  import { timecode } from '#lib/editor/timeline.ts';

  let { editor, onplay }: { editor: Editor; onplay?: () => void } = $props();

  // Drift (seconds, per 1× of speed) before the media element is re-seeked during forward play.
  const DRIFT = 0.15;

  let el: HTMLVideoElement | HTMLAudioElement | undefined = $state();
  let strip: HTMLCanvasElement | undefined = $state();
  let stripW = $state(0);
  let playing = $state(false);
  let raf = 0;
  let from = 0;
  let startedAt = 0;
  let rate = 1;
  let scrubbing = false;

  const src = $derived(editor.source);
  const media = $derived(editor.sourceMedia);
  const fps = $derived(editor.seq.fps);
  const length = $derived(media ? editor.sourceLength() : 0);
  const subclip = $derived(src?.subclip ? editor.seq.subclips.find((x) => x.id === src.subclip) : undefined);
  const marked = $derived(src && (src.in !== null || src.out !== null) ? (src.out ?? length) - (src.in ?? 0) : null);
  const focused = $derived(editor.mode === 'clip' && editor.viewer === 'source');

  const snap = (t: number) => Math.round(t * fps) / fps;

  // Paused: keep the picture on the source playhead.
  $effect(() => {
    const t = src?.playhead ?? 0;
    if (el && !playing && Math.abs(el.currentTime - t) > 1e-3 && el.readyState > 0) el.currentTime = t;
  });

  // A different file stops playback.
  $effect(() => {
    void src?.media;
    return () => pause();
  });

  onMount(() => () => cancelAnimationFrame(raf));

  function tick(now: number) {
    if (!playing || !src) return;
    // A frame's timestamp can predate startedAt; reversing from the very end would then step past it and stop.
    const t = from + (rate * Math.max(0, now - startedAt)) / 1000;
    if (t >= length || (rate < 0 && t <= 0)) {
      editor.seekSource(snap(Math.min(length, Math.max(0, t))));
      pause();
      return;
    }
    src.playhead = t;
    if (el) {
      if (rate < 0) {
        // Media cannot play backwards: seek frame by frame, letting each seek land first.
        if (!el.seeking) el.currentTime = t;
      } else if (Math.abs(el.currentTime - t) > DRIFT * rate) {
        el.currentTime = t;
      }
    }
    raf = requestAnimationFrame(tick);
  }

  function start() {
    if (!src || !length) return;
    if (!playing) onplay?.();
    rate = editor.shuttle || 1;
    if (rate > 0 && src.playhead >= length - 1 / fps) src.playhead = 0;
    if (rate < 0 && src.playhead <= 1 / fps) src.playhead = length;
    from = src.playhead;
    startedAt = performance.now();
    if (el) {
      el.currentTime = from;
      if (rate > 0) {
        el.playbackRate = Math.min(16, rate);
        el.muted = false;
        el.play().catch(() => {});
      } else {
        el.pause();
        el.muted = true;
      }
    }
    if (playing) return;
    playing = true;
    raf = requestAnimationFrame(tick);
  }

  export function play() {
    if (playing || !src) return;
    if (!playing) onplay?.();
    if (editor.shuttle <= 0) editor.shuttle = 1;
    start();
  }

  export function pause() {
    if (!playing) return;
    playing = false;
    editor.stopShuttle();
    cancelAnimationFrame(raf);
    el?.pause();
    if (src) src.playhead = snap(src.playhead);
  }

  export function toggle() {
    if (playing) pause();
    else play();
  }

  /** J/K/L shuttle in the source viewer. */
  export function shuttle(key: 'j' | 'k' | 'l') {
    if (!src || !length) return;
    if (!playing) onplay?.();
    if (editor.shuttleKey(key) === 0) pause();
    else start();
  }

  export function step(seconds: number) {
    pause();
    if (src) editor.seekSource(snap(src.playhead + seconds));
  }

  export function home(end: boolean) {
    pause();
    editor.seekSource(end ? length : 0);
  }

  // ------------------------------------------------------------------ scrub bar
  $effect(() => {
    if (!strip) return;
    const observer = new ResizeObserver(([entry]) => (stripW = Math.round(entry.contentRect.width)));
    observer.observe(strip);
    return () => observer.disconnect();
  });

  $effect(() => {
    void editor.assetVersion;
    draw(src?.playhead ?? 0, src?.in ?? null, src?.out ?? null, src?.markers ?? []);
  });

  function draw(playhead: number, a: number | null, b: number | null, marks: number[]) {
    const g = strip?.getContext('2d');
    if (!strip || !g || !stripW) return;
    const h = strip.clientHeight;
    const dpr = window.devicePixelRatio || 1;
    strip.width = stripW * dpr;
    strip.height = h * dpr;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, stripW, h);
    if (!media || !length) return;
    const css = getComputedStyle(strip);
    const accent = css.getPropertyValue('--accent').trim() || '#2f8f6a';
    const px = (t: number) => (t / length) * stripW;
    const sprite = editor.thumbsFor(media);
    const levels = media.has_audio ? editor.peaksFor(media) : null;
    const filmH = sprite && media.thumbs ? (levels ? h - 18 : h) : 0;
    if (sprite && media.thumbs && filmH > 0) {
      const cellW = (filmH * media.thumbs.width) / media.thumbs.height;
      for (let x = 0; x < stripW; x += cellW) {
        const t = (x / stripW) * length;
        const i = media.kind === 'image' ? 0 : Math.min(media.thumbs.count - 1, Math.floor(t / media.thumbs.interval));
        g.drawImage(sprite, i * media.thumbs.width, 0, media.thumbs.width, media.thumbs.height, x, 0, cellW, filmH);
      }
    }
    if (levels) {
      const top = filmH;
      const band = h - top;
      const mid = top + band / 2;
      const pps = media.peaks_per_second;
      g.fillStyle = media.kind === 'audio' ? '#3d7fb8' : accent;
      for (let x = 0; x < stripW; x++) {
        const i0 = Math.floor((x / stripW) * length * pps);
        const i1 = Math.max(i0 + 1, Math.floor(((x + 1) / stripW) * length * pps));
        let peak = 0;
        for (let i = i0; i < i1 && i < levels.length; i++) peak = Math.max(peak, levels[i]);
        const amp = (peak / 255) * (band / 2);
        g.fillRect(x, mid - amp, 1, Math.max(1, amp * 2));
      }
    }
    // Everything outside the In/Out is dimmed.
    if (a !== null || b !== null) {
      g.fillStyle = 'rgb(0 0 0 / 0.55)';
      const x0 = px(a ?? 0);
      const x1 = px(b ?? length);
      g.fillRect(0, 0, x0, h);
      g.fillRect(x1, 0, stripW - x1, h);
      g.fillStyle = accent;
      g.fillRect(x0, 0, x1 - x0, 3);
    }
    g.fillStyle = '#f2c14e';
    for (const m of marks) g.fillRect(px(m) - 1, 0, 2, 8);
    g.fillStyle = '#e5484d';
    g.fillRect(px(playhead) - 1, 0, 2, h);
  }

  function seekFromPointer(e: PointerEvent) {
    if (!strip || !length) return;
    const r = strip.getBoundingClientRect();
    editor.seekSource(snap(((e.clientX - r.left) / r.width) * length));
  }

  function scrubDown(e: PointerEvent) {
    if (!src || e.button !== 0) return;
    pause();
    scrubbing = true;
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    seekFromPointer(e);
  }

  function scrubMove(e: PointerEvent) {
    if (scrubbing) seekFromPointer(e);
  }

  function scrubKey(e: KeyboardEvent) {
    if (!src) return;
    const big = e.shiftKey ? 1 : 1 / fps;
    const moves: Record<string, () => void> = {
      ArrowLeft: () => step(-big),
      ArrowRight: () => step(big),
      Home: () => home(false),
      End: () => home(true),
    };
    const run = moves[e.key];
    if (!run) return;
    e.preventDefault();
    e.stopPropagation();
    run();
  }

  function toggleTrack(kind: 'video' | 'audio') {
    if (src) src[kind] = !src[kind];
  }
</script>

<section
  class="monitor"
  class:focused
  aria-label="Source monitor"
  onpointerdowncapture={() => (editor.viewer = 'source')}
  onfocusin={() => (editor.viewer = 'source')}
>
  <header>
    <h2>Source</h2>
    <span class="name" title={media?.name}>
      {#if media}{subclip ? `${subclip.name} · ` : ''}{media.name}{:else}No clip open{/if}
    </span>
    {#if media}
      <div class="patch" role="group" aria-label="Use from the source">
        <button
          type="button"
          aria-pressed={src?.video}
          disabled={!media.has_video && media.kind !== 'image'}
          title="Use the picture in edits"
          onclick={() => toggleTrack('video')}>V</button
        >
        <button
          type="button"
          aria-pressed={src?.audio}
          disabled={!media.has_audio}
          title="Use the sound in edits"
          onclick={() => toggleTrack('audio')}>A</button
        >
      </div>
    {/if}
  </header>
  <div class="stage">
    {#if media && src}
      {#if media.kind === 'video'}
        <!-- Imported footage brings no caption track; this is an editing monitor, not a player. -->
        <!-- svelte-ignore a11y_media_has_caption -->
        <video
          bind:this={el}
          src={proxyUrl(media.id)}
          preload="auto"
          playsinline
          onloadedmetadata={() => el && (el.currentTime = src.playhead)}
          aria-label="Source picture"
        ></video>
      {:else if media.kind === 'audio'}
        <audio bind:this={el} src={proxyUrl(media.id)} preload="auto"></audio>
        <span class="note" aria-hidden="true">♪</span>
      {:else}
        <img src={proxyUrl(media.id)} alt={media.name} />
      {/if}
    {:else}
      <p class="hint empty">Double-click a clip in the bin, or select it and press Enter, to open it here.</p>
    {/if}
  </div>
  <canvas
    bind:this={strip}
    class="strip"
    role="slider"
    tabindex={src ? 0 : -1}
    aria-label="Source position"
    aria-valuemin={0}
    aria-valuemax={length}
    aria-valuenow={src?.playhead ?? 0}
    aria-valuetext={timecode(src?.playhead ?? 0, fps)}
    onpointerdown={scrubDown}
    onpointermove={scrubMove}
    onpointerup={() => (scrubbing = false)}
    onpointercancel={() => (scrubbing = false)}
    onkeydown={scrubKey}
  ></canvas>
  <div class="transport">
    <span class="tc" aria-label="Source playhead time">
      {timecode(src?.playhead ?? 0, fps)}
      {#if playing && editor.shuttle !== 1}
        <span class="rate" aria-label="Shuttle speed">{editor.shuttle < 0 ? '◀' : '▶'} {Math.abs(editor.shuttle)}×</span
        >
      {/if}
    </span>
    <div class="buttons">
      <button
        type="button"
        disabled={!src}
        aria-label="Mark source In"
        title="Mark In (I)"
        onclick={() => src && editor.setSourceIn(src.playhead)}>{'{'}</button
      >
      <button
        type="button"
        disabled={!src}
        aria-label="Back one frame"
        title="Back one frame (Left)"
        onclick={() => step(-1 / fps)}
      >
        <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M11 3L5 8l6 5z" /></svg>
      </button>
      <button
        type="button"
        class="play"
        disabled={!src}
        aria-label={playing ? 'Pause source' : 'Play source'}
        title="Play or pause (Space)"
        onclick={toggle}
      >
        {#if playing}
          <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M5 3v10M11 3v10" /></svg>
        {:else}
          <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M5 3l8 5-8 5z" /></svg>
        {/if}
      </button>
      <button
        type="button"
        disabled={!src}
        aria-label="Forward one frame"
        title="Forward one frame (Right)"
        onclick={() => step(1 / fps)}
      >
        <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M5 3l6 5-6 5z" /></svg>
      </button>
      <button
        type="button"
        disabled={!src}
        aria-label="Mark source Out"
        title="Mark Out (O)"
        onclick={() => src && editor.setSourceOut(src.playhead)}>{'}'}</button
      >
      <button
        type="button"
        disabled={!src || (src.in === null && src.out === null)}
        aria-label="Clear source In and Out"
        title="Clear In and Out (Alt+X)"
        onclick={() => editor.clearSourceMarks()}>×</button
      >
    </div>
    <span class="tc muted" aria-label="Marked length">
      {marked === null ? timecode(length, fps) : `In–Out ${timecode(marked, fps)}`}
    </span>
  </div>
  <div class="edits">
    <button
      type="button"
      class="btn small"
      disabled={!src}
      title="Insert (,)"
      onclick={() => editor.sourceEdit('insert')}>Insert</button
    >
    <button
      type="button"
      class="btn small"
      disabled={!src}
      title="Overwrite (.)"
      onclick={() => editor.sourceEdit('overwrite')}>Overwrite</button
    >
    <button
      type="button"
      class="btn secondary small"
      disabled={!src}
      title="Append to the end (Shift+.)"
      onclick={() => editor.sourceEdit('append')}>Append</button
    >
    <button
      type="button"
      class="btn secondary small"
      disabled={!src}
      title="Make a subclip from the In and Out (Cmd/Ctrl+U)"
      onclick={() => editor.makeSubclip()}>Subclip</button
    >
  </div>
</section>

<style>
  .monitor {
    display: flex;
    flex-direction: column;
    min-width: 0;
    min-height: 0;
    background: var(--bg);
    border-right: 1px solid var(--line);
    box-shadow: inset 0 2px 0 transparent;
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
  .patch {
    display: flex;
    gap: 2px;
  }
  .patch button,
  .buttons button {
    min-width: 26px;
    height: 24px;
    padding: 0 5px;
    font: inherit;
    font-size: 0.8rem;
    font-weight: 700;
    color: var(--ink);
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 5px;
    cursor: pointer;
  }
  .patch button[aria-pressed='true'] {
    color: var(--accent-ink);
    background: var(--accent);
    border-color: var(--accent);
  }
  button:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
  .stage {
    position: relative;
    flex: 1;
    min-height: 0;
    display: grid;
    place-items: center;
    padding: 0 10px;
    background: #000;
  }
  video,
  img {
    display: block;
    width: 100%;
    height: 100%;
    min-height: 0;
    object-fit: contain;
  }
  .note {
    color: #6ea8d8;
    font-size: 3rem;
  }
  .empty {
    color: #c9d1cc;
    text-align: center;
    max-width: 20em;
    margin: 0;
  }
  .strip {
    display: block;
    width: 100%;
    height: 44px;
    background: var(--card);
    border-top: 1px solid var(--line);
    cursor: ew-resize;
    touch-action: none;
  }
  .strip:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: -2px;
  }
  .transport {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    padding: 6px 10px 2px;
    background: var(--card);
  }
  .buttons {
    display: flex;
    gap: 3px;
  }
  .buttons svg {
    width: 12px;
    height: 12px;
    stroke-linejoin: round;
    fill: currentColor;
    stroke: currentColor;
    stroke-width: 1.5;
  }
  .buttons .play {
    min-width: 32px;
  }
  .tc {
    font-variant-numeric: tabular-nums;
    font-size: 0.8rem;
  }
  .muted {
    color: var(--muted);
  }
  .rate {
    margin-left: 6px;
    padding: 0 5px;
    border-radius: 4px;
    font-size: 0.75rem;
    color: var(--accent-ink);
    background: var(--accent);
  }
  .edits {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    padding: 4px 10px 8px;
    background: var(--card);
  }
  .small {
    padding: 4px 10px;
    font-size: 0.8rem;
  }
</style>
