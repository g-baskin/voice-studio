<script lang="ts">
  import { onDestroy } from 'svelte';
  import * as api from '#lib/editor/api.ts';
  import type { Editor } from '#lib/editor/editor.svelte.ts';
  import { timecode } from '#lib/editor/timeline.ts';
  import type { ExportJob } from '#lib/editor/types.ts';

  let { editor }: { editor: Editor } = $props();

  let dialog: HTMLDialogElement | undefined = $state();
  let range = $state<'all' | 'inout'>('all');
  let quality = $state('standard');
  let job = $state<ExportJob | null>(null);
  let error = $state('');
  let timer: ReturnType<typeof setTimeout> | undefined;

  const seq = $derived(editor.seq);
  const hasRange = $derived(seq.range_in !== null || seq.range_out !== null);
  const running = $derived(job?.status === 'running');
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
      job = await api.startExport($state.snapshot(seq), range === 'inout', quality);
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
      <label
        >Quality
        <select bind:value={quality}>
          <option value="high">High (slower, larger)</option>
          <option value="standard">Standard</option>
          <option value="draft">Draft (fast check)</option>
        </select>
      </label>
      <p class="hint">
        {seq.width} × {seq.height} at {seq.fps} fps, rendered from your original files, not the previews.
      </p>
    </fieldset>

    {#if job}
      <div class="job" role="status" aria-live="polite">
        {#if job.status === 'running'}
          <progress max="1" value={job.progress}></progress>
          <span>Exporting... {Math.round(job.progress * 100)}%</span>
        {:else if job.status === 'done'}
          <a class="btn" href={api.exportFileUrl(job.id)} download={job.name}>Download {job.name}</a>
        {:else if job.status === 'cancelled'}
          <span>Export cancelled.</span>
        {/if}
      </div>
    {/if}
    {#if error}<p class="error" role="alert">{error}</p>{/if}

    <div class="row">
      {#if running}
        <button type="button" class="btn secondary" onclick={cancel}>Cancel export</button>
      {:else}
        <button type="button" class="btn" disabled={!editor.duration} onclick={start}>Export video</button>
      {/if}
      <button type="button" class="btn secondary" disabled={!editor.seq.clips.length} onclick={premiere}
        >Premiere Pro XML</button
      >
      <button class="btn secondary" value="close">Close</button>
    </div>
    <p class="hint">
      The Premiere Pro file (FCP 7 XML) keeps cuts, tracks, dissolves, speed, opacity, levels and markers. It points at
      the original files on this computer. Scale, position and ducking are not carried over.
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
