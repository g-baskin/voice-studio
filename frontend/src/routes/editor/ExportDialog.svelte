<script lang="ts">
  import { onDestroy } from 'svelte';
  import * as api from '#lib/editor/api.ts';
  import type { Editor } from '#lib/editor/editor.svelte.ts';
  import { markerRanges, subclipRanges, timecode } from '#lib/editor/timeline.ts';
  import type { ExportJob } from '#lib/editor/types.ts';

  let { editor }: { editor: Editor } = $props();

  let dialog: HTMLDialogElement | undefined = $state();
  let range = $state<'all' | 'inout' | 'markers' | 'subclips'>('all');
  let quality = $state('standard');
  let burn = $state(true);
  let job = $state<ExportJob | null>(null);
  let error = $state('');
  let timer: ReturnType<typeof setTimeout> | undefined;

  const seq = $derived(editor.seq);
  const hasRange = $derived(seq.range_in !== null || seq.range_out !== null);
  const captioned = $derived(!!seq.captions?.enabled && editor.captionPages.length > 0);
  const running = $derived(job?.status === 'running');
  const MAX_BATCH = 50;
  const byMarker = $derived(markerRanges(seq, editor.duration));
  const bySubclip = $derived(subclipRanges(seq));
  const batch = $derived(range === 'markers' ? byMarker : range === 'subclips' ? bySubclip.ranges : null);
  const files = $derived(job?.files ?? []);
  const rangeText = $derived(
    `${timecode(seq.range_in ?? 0, seq.fps)} to ${timecode(seq.range_out ?? editor.duration, seq.fps)}`,
  );

  onDestroy(() => clearTimeout(timer));

  export function open() {
    error = '';
    if (!running) job = null;
    range = hasRange ? 'inout' : 'all';
    dialog?.showModal();
  }

  function poll(id: string) {
    timer = setTimeout(async () => {
      try {
        job = await api.exportStatus(id);
        if (job.status === 'running') poll(id);
        else if (job.status === 'error') error = job.error ?? 'The export failed.';
      } catch (e) {
        error = e instanceof Error ? e.message : 'Lost track of the export.';
      }
    }, 700);
  }

  async function start() {
    error = '';
    try {
      const ranges = batch ? $state.snapshot(batch).slice(0, MAX_BATCH) : null;
      const out = $state.snapshot(seq) as typeof seq;
      // Leaving captions out of one export does not change the sequence.
      if (out.captions && !burn) out.captions = { ...out.captions, enabled: false };
      job = await api.startExport(out, range === 'inout', quality, ranges);
      poll(job.id);
    } catch (e) {
      error = e instanceof Error ? e.message : 'Could not start the export.';
    }
  }

  async function cancel() {
    if (!job) return;
    clearTimeout(timer);
    try {
      job = await api.cancelExport(job.id);
      poll(job.id);
    } catch (e) {
      error = e instanceof Error ? e.message : 'Could not cancel.';
    }
  }

  async function premiere() {
    error = '';
    await editor.save();
    if (editor.saveState !== 'saved' || !editor.seqId) {
      error = 'Save the sequence first; it could not be saved.';
      return;
    }
    try {
      const response = await api.call(`/sequences/${editor.seqId}/premiere.xml`);
      const name = /filename="([^"]+)"/.exec(response.headers.get('content-disposition') ?? '')?.[1] ?? 'sequence.xml';
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = url;
      link.download = name;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      error = e instanceof Error ? e.message : 'Could not make the Premiere Pro file.';
    }
  }
</script>

<dialog bind:this={dialog} aria-labelledby="export-title">
  <form method="dialog" class="box">
    <h2 id="export-title">Export</h2>

    <fieldset disabled={running}>
      <legend>Video (MP4, H.264 + AAC)</legend>
      <label class="radio"
        ><input type="radio" name="range" value="all" bind:group={range} />Whole sequence ({timecode(
          editor.duration,
          seq.fps,
        )})</label
      >
      <label class="radio" class:off={!hasRange}
        ><input type="radio" name="range" value="inout" bind:group={range} disabled={!hasRange} />In to out {hasRange
          ? `(${rangeText})`
          : '(mark with I and O)'}</label
      >
      <label class="radio" class:off={!byMarker.length}
        ><input type="radio" name="range" value="markers" bind:group={range} disabled={!byMarker.length} />Each marker
        to the next, as its own file {byMarker.length ? `(${byMarker.length})` : '(add markers with M)'}</label
      >
      <label class="radio" class:off={!bySubclip.ranges.length}
        ><input type="radio" name="range" value="subclips" bind:group={range} disabled={!bySubclip.ranges.length} />Each
        subclip in the sequence, as its own file {bySubclip.ranges.length
          ? `(${bySubclip.ranges.length})`
          : '(none used yet)'}</label
      >
      {#if batch}
        <p class="hint">
          {#if batch.length > MAX_BATCH}Only the first {MAX_BATCH} of {batch.length} are exported.{/if}
          {#if range === 'subclips' && bySubclip.unused}
            {bySubclip.unused} subclip{bySubclip.unused === 1 ? ' is' : 's are'} not in the sequence and will be skipped.
          {/if}
          Each file is named after the sequence, its number and its {range === 'markers' ? 'marker' : 'subclip'} name.
        </p>
      {/if}
      <label
        >Quality
        <select bind:value={quality}>
          <option value="high">High (slower, larger)</option>
          <option value="standard">Standard</option>
          <option value="draft">Draft (fast check)</option>
        </select>
      </label>
      {#if captioned}
        <label class="radio"><input type="checkbox" bind:checked={burn} />Burn in captions</label>
        {#if burn}
          <p class="hint">Captioned exports take a little longer and can be up to 30 minutes long.</p>
        {/if}
      {/if}
      <p class="hint">
        {seq.width} × {seq.height} at {seq.fps} fps, rendered from your original files, not the previews.
      </p>
    </fieldset>

    {#if job}
      <div class="job" role="status" aria-live="polite">
        {#if job.status === 'running'}
          <progress max="1" value={job.progress}></progress>
          <span
            >Exporting{files.length > 1 ? ` file ${Math.min(job.done + 1, files.length)} of ${files.length}` : ''}...
            {Math.round(job.progress * 100)}%</span
          >
        {:else if job.status === 'done' && files.length <= 1}
          <a class="btn" href={api.exportFileUrl(job.id)} download={job.name}>Download {job.name}</a>
        {:else if job.status === 'done'}
          <span>All {files.length} files exported. Download each one below.</span>
        {:else if job.status === 'cancelled'}
          <span>Export cancelled.{files.length > 1 ? ` ${job.done} of ${files.length} files finished.` : ''}</span>
        {/if}
      </div>
      {#if files.length > 1 && job.done}
        <ul class="files" aria-label="Exported files">
          {#each files.slice(0, job.done) as name, i (name)}
            <li><a href={api.exportFileUrl(job.id, i)} download={name}>{name}</a></li>
          {/each}
        </ul>
      {/if}
    {/if}
    {#if error}<p class="error" role="alert">{error}</p>{/if}

    <div class="row">
      {#if running}
        <button type="button" class="btn secondary" onclick={cancel}>Cancel export</button>
      {:else}
        <button type="button" class="btn" disabled={!editor.duration || batch?.length === 0} onclick={start}
          >{batch
            ? `Export ${Math.min(batch.length, MAX_BATCH)} file${batch.length === 1 ? '' : 's'}`
            : 'Export video'}</button
        >
      {/if}
      <button type="button" class="btn secondary" disabled={!editor.seq.clips.length} onclick={premiere}
        >Premiere Pro XML</button
      >
      <button class="btn secondary" value="close">Close</button>
    </div>
    <p class="hint">
      The Premiere Pro file (FCP 7 XML) keeps cuts, tracks, dissolves, speed, opacity, levels and markers. It points at
      the original files on this computer. Scale, position, ducking and captions are not carried over; download an SRT
      from the Captions tab for those.
    </p>
  </form>
</dialog>

<style>
  dialog {
    border: 1px solid var(--line);
    border-radius: var(--radius);
    background: var(--card);
    color: var(--ink);
    padding: 0;
    width: min(520px, calc(100vw - 32px));
  }
  dialog::backdrop {
    background: rgb(0 0 0 / 0.45);
  }
  .box {
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding: 20px;
  }
  h2 {
    margin: 0;
    font-size: 1.15rem;
  }
  fieldset {
    display: flex;
    flex-direction: column;
    gap: 8px;
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 10px 14px 12px;
    margin: 0;
  }
  legend {
    font-weight: 600;
    padding: 0 4px;
  }
  label {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  label.radio {
    flex-direction: row;
    align-items: center;
    gap: 8px;
    font-weight: 500;
  }
  label.off {
    color: var(--muted);
  }
  .job {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  progress {
    flex: 1;
    accent-color: var(--accent);
  }
  .files {
    margin: 0;
    padding: 0 0 0 18px;
    max-height: 160px;
    overflow: auto;
    font-size: 0.9rem;
  }
  .files a {
    color: var(--accent);
    overflow-wrap: anywhere;
  }
  .row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  .hint,
  .error {
    margin: 0;
    font-size: 0.85rem;
  }
</style>
