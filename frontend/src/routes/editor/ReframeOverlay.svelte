<script lang="ts">
  import type { Editor } from '#lib/editor/editor.svelte.ts';
  import { placement } from '#lib/editor/timeline.ts';

  let { editor, canvas }: { editor: Editor; canvas: HTMLCanvasElement | undefined } = $props();

  // Where the canvas draws the sequence frame inside the stage (it keeps its shape with object-fit: contain).
  let rect = $state({ x: 0, y: 0, w: 0, h: 0 });
  let drag = $state<{
    id: string;
    x0: number;
    y0: number;
    x: number;
    y: number;
    scale: number;
    zoom: boolean;
  } | null>(null);

  function measure() {
    if (!canvas) return;
    const k = Math.min(canvas.clientWidth / editor.seq.width, canvas.clientHeight / editor.seq.height);
    const w = editor.seq.width * k;
    const h = editor.seq.height * k;
    rect = {
      x: canvas.offsetLeft + (canvas.clientWidth - w) / 2,
      y: canvas.offsetTop + (canvas.clientHeight - h) / 2,
      w,
      h,
    };
  }

  $effect(() => {
    void editor.seq.width;
    void editor.seq.height;
    if (!canvas) return;
    measure();
    const watch = new ResizeObserver(measure);
    watch.observe(canvas);
    return () => watch.disconnect();
  });

  // The selected picture clip, else the top picture at the playhead.
  const target = $derived.by(() => {
    const picture = editor.layers.filter((l) => l.picture);
    if (editor.selected.length === 1) {
      const chosen = picture.find((l) => l.clip.id === editor.selected[0].id);
      if (chosen) return chosen;
    }
    const t = editor.playhead;
    return picture.filter((l) => t >= l.t0 && t < l.t1).sort((a, b) => b.z - a.z)[0] ?? null;
  });
  const box = $derived(target ? placement(editor.seq, target.clip, target.media) : null);
  const locked = $derived(target ? editor.isLocked(target.clip) : false);

  function down(e: PointerEvent) {
    if (e.button !== 0 || !target || locked || !rect.w) return;
    e.preventDefault();
    const c = target.clip;
    editor.selection = [c.id];
    editor.beginGesture();
    drag = { id: c.id, x0: e.clientX, y0: e.clientY, x: c.x, y: c.y, scale: c.scale, zoom: e.altKey };
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  }

  function move(e: PointerEvent) {
    if (!drag) return;
    const dx = (e.clientX - drag.x0) / rect.w;
    const dy = (e.clientY - drag.y0) / rect.h;
    // Alt+drag scales: up enlarges, down shrinks, doubling per frame height.
    if (drag.zoom) editor.reframe(drag.id, { scale: drag.scale * 2 ** -dy });
    else editor.reframe(drag.id, { x: drag.x + dx, y: drag.y + dy });
  }

  function up() {
    if (!drag) return;
    drag = null;
    editor.endGesture();
  }

  function cancel() {
    if (!drag) return;
    drag = null;
    editor.cancelGesture();
  }

  // Arrows move by 1% (Shift: 10%); Alt+Up/Down scales.
  function key(e: KeyboardEvent) {
    if (e.key === 'Escape' && drag) {
      e.stopPropagation();
      cancel();
      return;
    }
    const dir = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[e.key];
    if (!dir || !target || locked) return;
    e.preventDefault();
    e.stopPropagation();
    const c = target.clip;
    const step = e.shiftKey ? 0.1 : 0.01;
    editor.beginGesture();
    if (e.altKey) {
      if (dir[1]) editor.reframe(c.id, { scale: c.scale * (1 - dir[1] * step * 5) });
    } else editor.reframe(c.id, { x: c.x + dir[0] * step, y: c.y + dir[1] * step });
    editor.endGesture();
  }
</script>

<button
  type="button"
  class="reframe"
  class:grabbing={drag !== null}
  class:idle={!target || locked}
  style:left="{rect.x}px"
  style:top="{rect.y}px"
  style:width="{rect.w}px"
  style:height="{rect.h}px"
  aria-label={target
    ? `Reframe ${target.media.name}: drag or use the arrow keys to move the picture, Alt to scale`
    : 'Reframe: no picture at the playhead'}
  onpointerdown={down}
  onpointermove={move}
  onpointerup={up}
  onpointercancel={cancel}
  onlostpointercapture={up}
  onkeydown={key}
>
  {#if box && target}
    <span
      class="picture"
      style:left="{box.x * 100}%"
      style:top="{box.y * 100}%"
      style:width="{box.w * 100}%"
      style:height="{box.h * 100}%"
    ></span>
    <span class="readout"
      >{locked
        ? 'Track locked'
        : `x ${target.clip.x.toFixed(2)} · y ${target.clip.y.toFixed(2)} · ${Math.round(target.clip.scale * 100)}%`}</span
    >
  {:else}
    <span class="readout">No picture at the playhead</span>
  {/if}
</button>

<style>
  .reframe {
    position: absolute;
    box-sizing: border-box;
    margin: 0;
    padding: 0;
    font: inherit;
    border: 0;
    border-radius: 0;
    outline: 2px solid var(--accent);
    outline-offset: 0;
    cursor: grab;
    touch-action: none;
    /* Thirds guides for placing a face or subject. */
    background:
      linear-gradient(
        to right,
        transparent calc(33.33% - 0.5px),
        rgb(255 255 255 / 0.35) 0,
        rgb(255 255 255 / 0.35) calc(33.33% + 0.5px),
        transparent 0,
        transparent calc(66.67% - 0.5px),
        rgb(255 255 255 / 0.35) 0,
        rgb(255 255 255 / 0.35) calc(66.67% + 0.5px),
        transparent 0
      ),
      linear-gradient(
        to bottom,
        transparent calc(33.33% - 0.5px),
        rgb(255 255 255 / 0.35) 0,
        rgb(255 255 255 / 0.35) calc(33.33% + 0.5px),
        transparent 0,
        transparent calc(66.67% - 0.5px),
        rgb(255 255 255 / 0.35) 0,
        rgb(255 255 255 / 0.35) calc(66.67% + 0.5px),
        transparent 0
      );
  }
  .reframe:focus-visible {
    outline-width: 3px;
  }
  .reframe.grabbing {
    cursor: grabbing;
  }
  .reframe.idle {
    cursor: default;
  }
  .picture {
    display: block;
    position: absolute;
    box-sizing: border-box;
    border: 1px dashed rgb(255 255 255 / 0.8);
    pointer-events: none;
  }
  .readout {
    position: absolute;
    left: 50%;
    bottom: 6px;
    transform: translateX(-50%);
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.75rem;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
    color: #fff;
    background: rgb(0 0 0 / 0.75);
    pointer-events: none;
  }
</style>
