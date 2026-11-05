<script lang="ts">
  import type { Editor } from '#lib/editor/editor.svelte.ts';
  import {
    clamp,
    clipDuration,
    clipEnd,
    MAX_ZOOM,
    MEDIA_TYPE,
    MIN_ZOOM,
    onTrack,
    rulerStep,
    shortTime,
    SNAP_PX,
    snap,
    snapPoints,
    timecode,
    toFrame,
    trimLimits,
  } from '#lib/editor/timeline.ts';
  import type { Clip, Track } from '#lib/editor/types.ts';

  let { editor }: { editor: Editor } = $props();

  const HEAD_W = 172;
  const RULER_H = 30;
  const HEIGHT = { video: 62, audio: 50 } as const;

  let scroller: HTMLDivElement | undefined = $state();
  let grid: HTMLDivElement | undefined = $state();
  let rulerCanvas: HTMLCanvasElement | undefined = $state();
  let scrollLeft = $state(0);
  let viewW = $state(800);
  let theme = $state(0);
  const arts = new Map<string, HTMLCanvasElement>();

  const zoom = $derived(editor.zoom);
  const seq = $derived(editor.seq);
  const visibleW = $derived(Math.max(0, viewW - HEAD_W));
  const contentW = $derived(Math.max(visibleW, (editor.duration + 30) * zoom, (editor.playhead + 10) * zoom));
  const zoomSlider = $derived(Math.round((Math.log(zoom / MIN_ZOOM) / Math.log(MAX_ZOOM / MIN_ZOOM)) * 100));
  const selectedIds = $derived(new Set(editor.selection));

  function art(node: HTMLCanvasElement, id: string) {
    arts.set(id, node);
    return { destroy: () => arts.delete(id) };
  }

  // ------------------------------------------------------------------ zoom and scrolling
  export function setZoom(next: number, anchor = editor.playhead) {
    if (!scroller) return;
    const screen = anchor * zoom - scroller.scrollLeft;
    editor.zoom = clamp(next, MIN_ZOOM, MAX_ZOOM);
    requestAnimationFrame(() => {
      if (scroller) scroller.scrollLeft = Math.max(0, anchor * editor.zoom - screen);
    });
  }

  export function zoomToFit() {
    setZoom((visibleW - 40) / Math.max(editor.duration, 10), 0);
    if (scroller) scroller.scrollLeft = 0;
  }

  $effect(() => {
    // Keep the playhead in view while playing, as editors page the timeline forward.
    const x = editor.playhead * zoom;
    if (!editor.playing || !scroller) return;
    if (x > scroller.scrollLeft + visibleW - 24 || x < scroller.scrollLeft) scroller.scrollLeft = Math.max(0, x - 40);
  });

  $effect(() => {
    const query = matchMedia('(prefers-color-scheme: dark)');
    const bump = () => (theme += 1);
    query.addEventListener('change', bump);
    return () => query.removeEventListener('change', bump);
  });

  // ------------------------------------------------------------------ drawing
  function colors() {
    const style = getComputedStyle(document.documentElement);
    const v = (name: string) => style.getPropertyValue(name).trim();
    return { ink: v('--ink'), muted: v('--muted'), line: v('--line'), accent: v('--accent'), card: v('--card') };
  }

  function prepare(canvas: HTMLCanvasElement, w: number, h: number) {
    const dpr = window.devicePixelRatio || 1;
    if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
    }
    const g = canvas.getContext('2d');
    g?.setTransform(dpr, 0, 0, dpr, 0, 0);
    g?.clearRect(0, 0, w, h);
    return g;
  }

  function drawRuler() {
    if (!rulerCanvas) return;
    const g = prepare(rulerCanvas, visibleW, RULER_H);
    if (!g) return;
    const c = colors();
    const { major, minor } = rulerStep(zoom);
    const from = scrollLeft / zoom;
    const to = (scrollLeft + visibleW) / zoom;
    if (seq.range_in !== null || seq.range_out !== null) {
      const a = (seq.range_in ?? 0) * zoom - scrollLeft;
      const b = (seq.range_out ?? editor.duration) * zoom - scrollLeft;
      g.fillStyle = c.accent;
      g.globalAlpha = 0.25;
      g.fillRect(a, 0, b - a, RULER_H);
      g.globalAlpha = 1;
    }
    g.strokeStyle = c.muted;
    g.fillStyle = c.muted;
    g.font = '11px system-ui, sans-serif';
    g.beginPath();
    for (let t = Math.floor(from / minor) * minor; t <= to; t += minor) {
      const x = Math.round(t * zoom - scrollLeft) + 0.5;
      const isMajor = Math.abs(t / major - Math.round(t / major)) < 1e-6;
      g.moveTo(x, RULER_H);
      g.lineTo(x, isMajor ? 12 : 22);
      if (isMajor) g.fillText(major < 1 ? shortTime(t) : timecode(t, seq.fps).replace(/^00:/, ''), x + 4, 11);
    }
    g.stroke();
    g.fillStyle = c.accent;
    for (const m of seq.markers) {
      const x = m.time * zoom - scrollLeft;
      g.beginPath();
      g.moveTo(x - 5, RULER_H - 10);
      g.lineTo(x + 5, RULER_H - 10);
      g.lineTo(x, RULER_H - 3);
      g.fill();
    }
  }

  function drawLane(t: Track) {
    const canvas = arts.get(t.id);
    if (!canvas) return;
    const h = HEIGHT[t.kind];
    const g = prepare(canvas, visibleW, h);
    if (!g) return;
    const c = colors();
    for (const clip of onTrack(seq, t.id)) {
      const x = clip.start * zoom - scrollLeft;
      const w = clipDuration(clip) * zoom;
      if (x + w < 0 || x > visibleW) continue;
      const m = editor.mediaById.get(clip.media);
      g.save();
      g.beginPath();
      g.roundRect(x, 1, w, h - 2, 5);
      g.clip();
      const tint = !m ? c.muted : m.kind === 'audio' ? '#3d7fb8' : m.kind === 'image' ? '#8a63b8' : c.accent;
      g.fillStyle = tint;
      g.globalAlpha = 0.28;
      g.fillRect(x, 0, w, h);
      g.globalAlpha = 1;
      if (m) {
        const sprite = editor.thumbsFor(m);
        const showWave = m.has_audio && !clip.muted && !t.muted;
        const filmH = m.kind === 'audio' || t.kind === 'audio' ? 0 : showWave ? h - 20 : h - 4;
        if (sprite && m.thumbs && filmH > 0) {
          const cellW = (filmH * m.thumbs.width) / m.thumbs.height;
          const first = Math.max(0, Math.floor(-x / cellW));
          for (let i = first, cx = x + first * cellW; cx < Math.min(x + w, visibleW); i++, cx += cellW) {
            const src = clip.source_in + ((cx - x) / zoom) * clip.speed;
            const idx = m.kind === 'image' ? 0 : Math.min(m.thumbs.count - 1, Math.floor(src / m.thumbs.interval));
            g.drawImage(sprite, idx * m.thumbs.width, 0, m.thumbs.width, m.thumbs.height, cx, 2, cellW, filmH);
          }
        }
        const levels = showWave ? editor.peaksFor(m) : null;
        if (levels) {
          const top = filmH ? filmH + 2 : 14;
          const band = h - top - 2;
          const mid = top + band / 2;
          const pps = m.peaks_per_second;
          const gain = Math.min(2, 10 ** ((clip.volume + t.volume) / 20));
          g.fillStyle = m.kind === 'audio' ? '#3d7fb8' : c.accent;
          g.globalAlpha = 0.9;
          for (let px = Math.max(0, Math.floor(x)); px < Math.min(x + w, visibleW); px++) {
            const s0 = clip.source_in + ((px - x) / zoom) * clip.speed;
            const i0 = Math.floor(s0 * pps);
            const i1 = Math.max(i0 + 1, Math.floor((s0 + clip.speed / zoom) * pps));
            let peak = 0;
            for (let i = i0; i < i1 && i < levels.length; i++) peak = Math.max(peak, levels[i]);
            const amp = Math.min(1, (peak / 255) * gain) * (band / 2);
            g.fillRect(px, mid - amp, 1, Math.max(1, amp * 2));
          }
          g.globalAlpha = 1;
        }
      }
      if (clip.fade_in || clip.fade_out) {
        g.strokeStyle = c.ink;
        g.globalAlpha = 0.6;
        g.beginPath();
        if (clip.fade_in) {
          g.moveTo(x, h - 2);
          g.lineTo(x + clip.fade_in * zoom, 2);
        }
        if (clip.fade_out) {
          g.moveTo(x + w - clip.fade_out * zoom, 2);
          g.lineTo(x + w, h - 2);
        }
        g.stroke();
        g.globalAlpha = 1;
      }
      g.restore();
    }
  }

  $effect(() => {
    void [theme, editor.assetVersion, zoom, scrollLeft, visibleW, seq.markers.length, seq.range_in, seq.range_out];
    drawRuler();
    for (const t of seq.tracks) drawLane(t);
  });

  // ------------------------------------------------------------------ pointer editing
  type Grab = {
    mode: 'move' | 'start' | 'end' | 'scrub';
    x0: number;
    started: boolean;
    primary: string;
    orig: Map<string, Clip>;
  };
  let grab: Grab | null = null;

  function timeAt(clientX: number): number {
    if (!scroller) return 0;
    const rect = scroller.getBoundingClientRect();
    return Math.max(0, (clientX - rect.left - HEAD_W + scroller.scrollLeft) / zoom);
  }

  function snapped(t: number, exclude: Set<string>): number {
    if (!editor.snapping) {
      editor.snapLine = null;
      return t;
    }
    const hit = snap(t, snapPoints(seq, editor.playhead, exclude), SNAP_PX / zoom);
    editor.snapLine = hit.to;
    return hit.time;
  }

  function scrubTo(clientX: number) {
    let t = timeAt(clientX);
    if (editor.snapping) {
      const points = [0, ...seq.markers.map((m) => m.time), ...seq.clips.flatMap((c) => [c.start, clipEnd(c)])];
      t = snap(t, points, SNAP_PX / zoom).time;
    }
    editor.playhead = toFrame(seq, t);
  }

  function down(e: PointerEvent) {
    if (e.button !== 0 || !(e.target instanceof Element) || !grid) return;
    const target = e.target;
    if (target.closest('[data-ruler]')) {
      grab = { mode: 'scrub', x0: e.clientX, started: true, primary: '', orig: new Map() };
      grid.setPointerCapture(e.pointerId);
      scrubTo(e.clientX);
      return;
    }
    const el = target.closest<HTMLElement>('[data-clip]');
    if (!el) {
      if (target.closest('[data-lane]')) editor.selection = [];
      return;
    }
    const clip = seq.clips.find((c) => c.id === el.dataset.clip);
    if (!clip) return;
    e.preventDefault();
    el.focus();
    if (editor.tool === 'razor' && !editor.isLocked(clip)) {
      let t = timeAt(e.clientX);
      if (editor.snapping && Math.abs(t - editor.playhead) * zoom < SNAP_PX) t = editor.playhead;
      editor.splitAt(t, [clip]);
      return;
    }
    if (e.shiftKey || e.metaKey || e.ctrlKey)
      editor.selection = selectedIds.has(clip.id)
        ? editor.selection.filter((id) => id !== clip.id)
        : [...editor.selection, clip.id];
    else if (!selectedIds.has(clip.id)) editor.selection = [clip.id];
    editor.selectedTrack = null;
    if (editor.isLocked(clip) || !editor.selection.includes(clip.id)) return;
    const edge = target.closest<HTMLElement>('[data-edge]')?.dataset.edge;
    const moving = edge ? [clip] : editor.selected.filter((c) => !editor.isLocked(c));
    grab = {
      mode: edge === 'start' ? 'start' : edge === 'end' ? 'end' : 'move',
      x0: e.clientX,
      started: false,
      primary: clip.id,
      orig: new Map(moving.map((c) => [c.id, $state.snapshot(c) as Clip])),
    };
    grid.setPointerCapture(e.pointerId);
  }

  function move(e: PointerEvent) {
    if (!grab) return;
    if (grab.mode === 'scrub') {
      scrubTo(e.clientX);
      return;
    }
    if (!grab.started) {
      if (Math.abs(e.clientX - grab.x0) < 3) return;
      grab.started = true;
      editor.beginGesture();
    }
    const dt = (e.clientX - grab.x0) / zoom;
    const base = grab.orig.get(grab.primary);
    const live = seq.clips.find((c) => c.id === grab?.primary);
    if (!base || !live) return;
    const exclude = new Set(grab.orig.keys());
    const m = editor.mediaById.get(base.media);
    if (grab.mode === 'move') {
      const length = clipDuration(base);
      const raw = base.start + dt;
      let start = raw;
      let line: number | null = null;
      if (editor.snapping) {
        // Either edge may snap; the closer one wins.
        const points = snapPoints(seq, editor.playhead, exclude);
        const a = snap(raw, points, SNAP_PX / zoom);
        const b = snap(raw + length, points, SNAP_PX / zoom);
        if (a.to !== null && (b.to === null || Math.abs(a.time - raw) <= Math.abs(b.time - raw - length))) {
          start = a.time;
          line = a.to;
        } else if (b.to !== null) {
          start = b.time - length;
          line = b.to;
        }
      }
      editor.snapLine = line;
      const earliest = Math.min(...[...grab.orig.values()].map((c) => c.start));
      const delta = Math.max(-earliest, toFrame(seq, start) - base.start);
      for (const [id, c] of grab.orig) {
        const target = seq.clips.find((x) => x.id === id);
        if (target) target.start = c.start + delta;
      }
      if (grab.orig.size === 1) {
        const lane = document.elementFromPoint(e.clientX, e.clientY)?.closest<HTMLElement>('[data-lane]');
        const to = seq.tracks.find((t) => t.id === lane?.dataset.lane);
        const from = seq.tracks.find((t) => t.id === base.track);
        if (to && from && to.kind === from.kind && !to.locked) live.track = to.id;
      }
    } else {
      const [lo, hi] = trimLimits(seq, base, m, grab.mode);
      if (grab.mode === 'start') {
        const start = toFrame(seq, clamp(snapped(base.start + dt, exclude), lo, hi));
        live.start = start;
        live.source_in = Math.max(0, base.source_in + (start - base.start) * base.speed);
      } else {
        const end = toFrame(seq, clamp(snapped(clipEnd(base) + dt, exclude), lo, hi));
        live.source_out = base.source_in + (end - base.start) * base.speed;
      }
    }
  }

  function up() {
    if (!grab) return;
    const done = grab;
    grab = null;
    if (done.mode === 'scrub' || !done.started) return;
    editor.endGesture(done.mode === 'move' ? [...done.orig.keys()] : []);
  }

  function escape(e: KeyboardEvent) {
    if (e.key === 'Escape' && grab?.started) {
      grab = null;
      editor.cancelGesture();
    }
  }

  // Bin items dragged onto a lane are placed there as an overwrite edit.
  function over(e: DragEvent) {
    if (e.dataTransfer?.types.includes(MEDIA_TYPE)) {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'copy';
    }
  }

  function drop(e: DragEvent) {
    const id = e.dataTransfer?.getData(MEDIA_TYPE);
    const m = id ? editor.mediaById.get(id) : undefined;
    if (!m || !(e.target instanceof Element)) return;
    e.preventDefault();
    const lane = e.target.closest<HTMLElement>('[data-lane]');
    editor.place(m, lane?.dataset.lane ?? null, snapped(timeAt(e.clientX), new Set()));
    editor.snapLine = null;
  }

  $effect(() => {
    const node = grid;
    if (!node) return;
    node.addEventListener('pointerdown', down);
    node.addEventListener('pointermove', move);
    node.addEventListener('pointerup', up);
    node.addEventListener('pointercancel', up);
    node.addEventListener('dragover', over);
    node.addEventListener('drop', drop);
    window.addEventListener('keydown', escape);
    return () => {
      node.removeEventListener('pointerdown', down);
      node.removeEventListener('pointermove', move);
      node.removeEventListener('pointerup', up);
      node.removeEventListener('pointercancel', up);
      node.removeEventListener('dragover', over);
      node.removeEventListener('drop', drop);
      window.removeEventListener('keydown', escape);
    };
  });

  // ------------------------------------------------------------------ keyboard
  function clipKey(e: KeyboardEvent, clip: Clip) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      e.stopPropagation();
      editor.selection = e.shiftKey
        ? selectedIds.has(clip.id)
          ? editor.selection.filter((id) => id !== clip.id)
          : [...editor.selection, clip.id]
        : [clip.id];
      return;
    }
    if (e.altKey && (e.key === 'ArrowLeft' || e.key === 'ArrowRight') && !editor.isLocked(clip)) {
      // Alt+arrow nudges by one frame, as in Premiere Pro.
      e.preventDefault();
      e.stopPropagation();
      const step = (e.key === 'ArrowLeft' ? -1 : 1) / seq.fps;
      const ids = selectedIds.has(clip.id) ? editor.selection : [clip.id];
      editor.beginGesture();
      for (const c of seq.clips) if (ids.includes(c.id)) c.start = toFrame(seq, Math.max(0, c.start + step));
      editor.endGesture(ids);
    }
  }

  function rulerKey(e: KeyboardEvent) {
    const step = e.shiftKey ? 1 : 1 / seq.fps;
    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
      e.preventDefault();
      e.stopPropagation();
      editor.playhead = toFrame(seq, Math.max(0, editor.playhead + (e.key === 'ArrowLeft' ? -step : step)));
    }
  }

  function clipLabel(c: Clip, t: Track): string {
    const name = editor.mediaById.get(c.media)?.name ?? 'Missing media';
    const extra = [c.speed !== 1 ? `${c.speed}× speed` : '', c.transition ? 'dissolve in' : '', c.muted ? 'muted' : '']
      .filter(Boolean)
      .join(', ');
    return `${name} on ${t.name}, starts ${timecode(c.start, seq.fps)}, ${clipDuration(c).toFixed(2)} seconds${extra ? ', ' + extra : ''}`;
  }

  function trackToggle(t: Track, key: 'muted' | 'hidden' | 'locked' | 'duck') {
    editor.commit(() => {
      t[key] = !t[key];
    });
  }
</script>

<section class="timeline" aria-label="Timeline">
  <div class="tools" role="toolbar" aria-label="Timeline tools">
    <div class="seg">
      <button
        type="button"
        aria-pressed={editor.tool === 'select'}
        title="Selection tool (V)"
        onclick={() => (editor.tool = 'select')}
      >
        <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 2l9 5-4 1-2 4z" /></svg>Select
      </button>
      <button
        type="button"
        aria-pressed={editor.tool === 'razor'}
        title="Razor tool (C): click a clip to cut it"
        onclick={() => (editor.tool = 'razor')}
      >
        <svg viewBox="0 0 16 16" aria-hidden="true"
          ><circle cx="4" cy="12" r="2" /><circle cx="12" cy="12" r="2" /><path d="M5 10l7-8M11 10L4 2" /></svg
        >Razor
      </button>
      <button
        type="button"
        aria-pressed={editor.snapping}
        title="Snapping (S)"
        onclick={() => (editor.snapping = !editor.snapping)}
      >
        <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 2v6a4 4 0 008 0V2M4 5h3M9 5h3" /></svg>Snap
      </button>
    </div>
    <div class="seg">
      <button type="button" title="Split at playhead (Ctrl+K or Ctrl+B)" onclick={() => editor.splitAt(editor.playhead)}
        >Split</button
      >
      <button
        type="button"
        title="Delete (Delete)"
        disabled={!editor.selection.length}
        onclick={() => editor.deleteSelected(false)}>Delete</button
      >
      <button
        type="button"
        title="Ripple delete: remove and close the gap (Shift+Delete)"
        disabled={!editor.selection.length}
        onclick={() => editor.deleteSelected(true)}>Ripple delete</button
      >
      <button
        type="button"
        title="Cross dissolve at the selected clip's start (Ctrl+D)"
        disabled={!editor.selection.length}
        onclick={() => editor.addDissolve()}>Dissolve</button
      >
    </div>
    <div class="seg">
      <button type="button" title="Add marker (M)" onclick={() => editor.addMarker(editor.playhead)}>Marker</button>
      <button type="button" title="Mark in (I)" onclick={() => editor.setIn(editor.playhead)}>In</button>
      <button type="button" title="Mark out (O)" onclick={() => editor.setOut(editor.playhead)}>Out</button>
    </div>
    <div class="seg">
      <button type="button" title="Add a video track" onclick={() => editor.commit(() => editor.addTrack('video'))}
        >+ Video track</button
      >
      <button type="button" title="Add an audio track" onclick={() => editor.commit(() => editor.addTrack('audio'))}
        >+ Audio track</button
      >
    </div>
    <div class="seg zoom">
      <button type="button" title="Zoom out (-)" aria-label="Zoom out" onclick={() => setZoom(zoom / 1.5)}>−</button>
      <input
        type="range"
        min="0"
        max="100"
        value={zoomSlider}
        aria-label="Timeline zoom"
        oninput={(e) => setZoom(MIN_ZOOM * (MAX_ZOOM / MIN_ZOOM) ** (Number(e.currentTarget.value) / 100))}
      />
      <button type="button" title="Zoom in (=)" aria-label="Zoom in" onclick={() => setZoom(zoom * 1.5)}>+</button>
      <button type="button" title="Zoom to fit (\)" onclick={zoomToFit}>Fit</button>
    </div>
  </div>

  <div
    class="scroll"
    class:razor={editor.tool === 'razor'}
    bind:this={scroller}
    bind:clientWidth={viewW}
    onscroll={() => (scrollLeft = scroller?.scrollLeft ?? 0)}
  >
    <div
      class="grid"
      bind:this={grid}
      style:width="{HEAD_W + contentW}px"
      style:grid-template-columns="{HEAD_W}px {contentW}px"
    >
      <div class="corner">{timecode(editor.playhead, seq.fps)}</div>
      <div
        class="ruler"
        data-ruler
        role="slider"
        tabindex="0"
        aria-label="Playhead"
        aria-valuemin={0}
        aria-valuemax={Math.max(editor.duration, editor.playhead)}
        aria-valuenow={editor.playhead}
        aria-valuetext={timecode(editor.playhead, seq.fps)}
        onkeydown={rulerKey}
      >
        <canvas bind:this={rulerCanvas} style:left="{scrollLeft}px" style:width="{visibleW}px"></canvas>
      </div>

      {#each seq.tracks as t (t.id)}
        <div
          class="head"
          class:selected={editor.selectedTrack === t.id}
          class:video={t.kind === 'video'}
          style:height="{HEIGHT[t.kind]}px"
        >
          <button
            type="button"
            class="name"
            aria-pressed={editor.selectedTrack === t.id}
            title="Track settings"
            onclick={() => {
              editor.selectedTrack = t.id;
              editor.selection = [];
            }}>{t.name}</button
          >
          <div class="toggles">
            {#if t.kind === 'video'}
              <button
                type="button"
                class="tog"
                aria-pressed={t.hidden}
                aria-label="Hide {t.name}"
                title="Hide track output"
                onclick={() => trackToggle(t, 'hidden')}
              >
                <svg viewBox="0 0 16 16" aria-hidden="true"
                  ><path d="M1 8s3-5 7-5 7 5 7 5-3 5-7 5-7-5-7-5z" /><circle cx="8" cy="8" r="2" />{#if t.hidden}<path
                      d="M2 14L14 2"
                    />{/if}</svg
                >
              </button>
            {/if}
            <button
              type="button"
              class="tog"
              aria-pressed={t.muted}
              aria-label="Mute {t.name}"
              title="Mute track"
              onclick={() => trackToggle(t, 'muted')}>M</button
            >
            {#if t.kind === 'audio'}
              <button
                type="button"
                class="tog"
                aria-pressed={t.duck}
                aria-label="Duck {t.name} under speech"
                title="Duck: lower this track while other tracks have sound (music beds)"
                onclick={() => trackToggle(t, 'duck')}>D</button
              >
            {/if}
            <button
              type="button"
              class="tog"
              aria-pressed={t.locked}
              aria-label="Lock {t.name}"
              title="Lock track"
              onclick={() => trackToggle(t, 'locked')}
            >
              <svg viewBox="0 0 16 16" aria-hidden="true"
                ><rect x="3" y="7" width="10" height="7" rx="1" /><path
                  d={t.locked ? 'M5 7V5a3 3 0 016 0v2' : 'M5 7V5a3 3 0 015.6-1.5'}
                /></svg
              >
            </button>
          </div>
        </div>
        <div class="lane" class:locked={t.locked} data-lane={t.id} style:height="{HEIGHT[t.kind]}px">
          <canvas class="art" use:art={t.id} style:left="{scrollLeft}px" style:width="{visibleW}px"></canvas>
          {#each onTrack(seq, t.id) as c (c.id)}
            {@const w = clipDuration(c) * zoom}
            {@const m = editor.mediaById.get(c.media)}
            <div
              class="clip"
              class:selected={selectedIds.has(c.id)}
              class:missing={!m}
              class:audio={m?.kind === 'audio'}
              data-clip={c.id}
              role="button"
              tabindex="0"
              aria-pressed={selectedIds.has(c.id)}
              aria-label={clipLabel(c, t)}
              style:left="{c.start * zoom}px"
              style:width="{Math.max(2, w)}px"
              onkeydown={(e) => clipKey(e, c)}
            >
              <span class="edge start" data-edge="start"></span>
              {#if w > 28}
                <span class="label">
                  {#if c.transition}<span class="fx" title="Cross dissolve">⋈</span>{/if}
                  {#if c.speed !== 1}<span class="fx">{c.speed}×</span>{/if}
                  {m?.name ?? 'Media offline'}
                </span>
              {/if}
              <span class="edge end" data-edge="end"></span>
            </div>
          {/each}
        </div>
      {/each}

      <div class="overlay" aria-hidden="true" style:grid-row="1 / span {seq.tracks.length + 1}">
        {#if seq.range_in !== null || seq.range_out !== null}
          <div
            class="range"
            style:left="{(seq.range_in ?? 0) * zoom}px"
            style:width="{((seq.range_out ?? editor.duration) - (seq.range_in ?? 0)) * zoom}px"
          ></div>
        {/if}
        {#each seq.markers as m (m.time)}
          <div class="marker" style:left="{m.time * zoom}px"></div>
        {/each}
        {#if editor.snapLine !== null}
          <div class="snap" style:left="{editor.snapLine * zoom}px"></div>
        {/if}
        <div class="playhead" style:left="{editor.playhead * zoom}px"></div>
      </div>
    </div>
  </div>
</section>

<style>
  .timeline {
    display: flex;
    flex-direction: column;
    min-height: 0;
    background: var(--card);
    border-top: 1px solid var(--line);
  }
  .tools {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 12px;
    align-items: center;
    padding: 6px 10px;
    border-bottom: 1px solid var(--line);
  }
  .seg {
    display: flex;
    gap: 2px;
    align-items: center;
  }
  .zoom {
    margin-left: auto;
  }
  .zoom input {
    width: 120px;
  }
  .tools button {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font: inherit;
    font-size: 0.82rem;
    font-weight: 500;
    color: var(--ink);
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 4px 8px;
    cursor: pointer;
  }
  .tools button:hover:not(:disabled) {
    background: var(--bg);
    border-color: var(--line);
  }
  .tools button[aria-pressed='true'] {
    background: color-mix(in srgb, var(--accent) 18%, transparent);
    border-color: var(--accent);
  }
  .tools button:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }
  svg {
    width: 14px;
    height: 14px;
    fill: none;
    stroke: currentColor;
    stroke-width: 1.4;
    stroke-linecap: round;
    stroke-linejoin: round;
  }
  .scroll {
    position: relative;
    flex: 1;
    min-height: 0;
    overflow: auto;
    overscroll-behavior: contain;
  }
  .scroll.razor .clip {
    cursor: crosshair;
  }
  .grid {
    position: relative;
    display: grid;
    grid-auto-rows: auto;
    user-select: none;
    touch-action: none;
  }
  /* Explicit columns: the overlay spans every row, so auto-placement would shift the cells. */
  .corner,
  .head {
    grid-column: 1;
    position: sticky;
    left: 0;
    z-index: 3;
    background: var(--card);
    border-right: 1px solid var(--line);
  }
  .corner {
    top: 0;
    z-index: 5;
    height: 30px;
    display: flex;
    align-items: center;
    padding: 0 10px;
    font-variant-numeric: tabular-nums;
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--accent);
    border-bottom: 1px solid var(--line);
  }
  .ruler,
  .lane {
    grid-column: 2;
  }
  .ruler {
    position: sticky;
    top: 0;
    z-index: 4;
    height: 30px;
    background: var(--card);
    border-bottom: 1px solid var(--line);
    cursor: ew-resize;
  }
  canvas {
    position: absolute;
    top: 0;
    height: 100%;
    pointer-events: none;
  }
  .head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 4px;
    padding: 0 6px 0 4px;
    border-bottom: 1px solid var(--line);
  }
  .head.video {
    background: color-mix(in srgb, var(--accent) 5%, var(--card));
  }
  .head.selected {
    box-shadow: inset 3px 0 0 var(--accent);
  }
  .name {
    font: inherit;
    font-weight: 600;
    font-size: 0.85rem;
    color: var(--ink);
    background: none;
    border: 0;
    padding: 4px 6px;
    border-radius: 5px;
    cursor: pointer;
    max-width: 70px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .name:hover {
    background: var(--bg);
  }
  .toggles {
    display: flex;
    gap: 2px;
  }
  .tog {
    width: 24px;
    height: 24px;
    display: grid;
    place-items: center;
    font: inherit;
    font-size: 0.72rem;
    font-weight: 700;
    color: var(--muted);
    background: var(--bg);
    border: 1px solid var(--line);
    border-radius: 5px;
    cursor: pointer;
    padding: 0;
  }
  .tog[aria-pressed='true'] {
    color: var(--accent-ink);
    background: var(--accent);
    border-color: var(--accent);
  }
  .lane {
    position: relative;
    border-bottom: 1px solid var(--line);
    background: color-mix(in srgb, var(--bg) 70%, var(--card));
  }
  .lane.locked {
    background-image: repeating-linear-gradient(
      135deg,
      transparent 0 6px,
      color-mix(in srgb, var(--line) 60%, transparent) 6px 7px
    );
  }
  .clip {
    position: absolute;
    top: 1px;
    bottom: 1px;
    border: 1px solid color-mix(in srgb, var(--accent) 70%, var(--line));
    border-radius: 5px;
    cursor: grab;
    overflow: hidden;
  }
  .clip.audio {
    border-color: #3d7fb8;
  }
  .clip.missing {
    border-style: dashed;
    border-color: var(--bad);
  }
  .clip.selected {
    border: 2px solid var(--ink);
    box-shadow: 0 0 0 1px var(--card);
  }
  .clip:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 1px;
  }
  .label {
    position: absolute;
    left: 6px;
    right: 6px;
    top: 2px;
    font-size: 0.72rem;
    font-weight: 600;
    color: var(--ink);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    text-shadow: 0 0 3px var(--card);
    pointer-events: none;
  }
  .fx {
    display: inline-block;
    padding: 0 3px;
    margin-right: 3px;
    border-radius: 3px;
    background: var(--card);
    color: var(--accent);
  }
  .edge {
    position: absolute;
    top: 0;
    bottom: 0;
    width: 7px;
    cursor: ew-resize;
    z-index: 1;
  }
  .edge.start {
    left: 0;
  }
  .edge.end {
    right: 0;
  }
  .clip.selected .edge {
    background: color-mix(in srgb, var(--ink) 25%, transparent);
  }
  .overlay {
    grid-column: 2;
    position: relative;
    pointer-events: none;
    z-index: 4;
  }
  .playhead,
  .snap,
  .marker {
    position: absolute;
    top: 0;
    bottom: 0;
    width: 0;
  }
  .playhead {
    border-left: 2px solid var(--bad);
    margin-left: -1px;
  }
  .playhead::before {
    content: '';
    position: absolute;
    top: 0;
    left: -7px;
    border: 6px solid transparent;
    border-top: 9px solid var(--bad);
  }
  .snap {
    border-left: 1px dashed var(--warn);
  }
  .marker {
    border-left: 1px solid color-mix(in srgb, var(--accent) 50%, transparent);
  }
  .range {
    position: absolute;
    top: 30px;
    bottom: 0;
    background: color-mix(in srgb, var(--accent) 7%, transparent);
  }
</style>
