<script lang="ts">
  import { thumbsUrl } from '#lib/editor/api.ts';
  import type { Editor } from '#lib/editor/editor.svelte.ts';
  import { MEDIA_TYPE, shortTime } from '#lib/editor/timeline.ts';
  import type { Media } from '#lib/editor/types.ts';

  let { editor }: { editor: Editor } = $props();

  const ACCEPT = '.mp4,.mov,.m4v,.webm,.mkv,.avi,.wav,.mp3,.m4a,.aac,.flac,.ogg,.opus,.aif,.aiff,.png,.jpg,.jpeg,.webp';
  let input: HTMLInputElement | undefined = $state();
  let dragging = $state(false);
  let filter = $state<'all' | 'video' | 'audio' | 'image'>('all');

  const shown = $derived(editor.media.filter((m) => filter === 'all' || m.kind === filter));

  function picked() {
    if (input?.files?.length) void editor.upload([...input.files]);
    if (input) input.value = '';
  }

  function dropFiles(e: DragEvent) {
    dragging = false;
    if (!e.dataTransfer?.files.length) return;
    e.preventDefault();
    void editor.upload([...e.dataTransfer.files]);
  }

  function overFiles(e: DragEvent) {
    if (e.dataTransfer?.types.includes('Files')) {
      e.preventDefault();
      dragging = true;
    }
  }

  function startDrag(e: DragEvent, m: Media) {
    if (!e.dataTransfer || m.status !== 'ready') {
      e.preventDefault();
      return;
    }
    e.dataTransfer.setData(MEDIA_TYPE, m.id);
    e.dataTransfer.effectAllowed = 'copy';
  }

  function detail(m: Media): string {
    if (m.status === 'processing' || m.status === 'uploading') return 'Preparing preview...';
    if (m.status === 'error') return m.error ?? 'Could not prepare this file.';
    const size = m.width ? `${m.width}×${m.height}` : '';
    return [m.kind === 'image' ? 'Still image' : shortTime(m.duration ?? 0), size].filter(Boolean).join(' · ');
  }

  function remove(m: Media) {
    if (confirm(`Remove ${m.name} from the bin? Its file is deleted from this computer's Editor data.`))
      void editor.removeMedia(m);
  }
</script>

<section
  class="bin"
  class:dragging
  aria-labelledby="bin-title"
  ondragover={overFiles}
  ondragleave={() => (dragging = false)}
  ondrop={dropFiles}
>
  <header>
    <h2 id="bin-title">Media</h2>
    <button type="button" class="btn small" onclick={() => input?.click()}>Import</button>
    <input bind:this={input} type="file" multiple accept={ACCEPT} hidden onchange={picked} />
  </header>
  <div class="filters" role="group" aria-label="Show">
    {#each ['all', 'video', 'audio', 'image'] as const as f (f)}
      <button type="button" aria-pressed={filter === f} onclick={() => (filter = f)}>
        {f === 'all' ? 'All' : f === 'video' ? 'Video' : f === 'audio' ? 'Audio' : 'Images'}
      </button>
    {/each}
  </div>
  {#if editor.uploads}
    <p class="hint">Uploading {editor.uploads} file{editor.uploads === 1 ? '' : 's'}...</p>
  {/if}
  {#if !editor.media.length}
    <div class="empty">
      <p>Drop video, audio or images here, or choose <strong>Import</strong>.</p>
      <p class="hint">Then drag them onto the timeline.</p>
    </div>
  {:else}
    <ul>
      {#each shown as m (m.id)}
        <li class:error={m.status === 'error'}>
          <div
            class="item"
            draggable={m.status === 'ready'}
            ondragstart={(e) => startDrag(e, m)}
            title={m.status === 'ready' ? 'Drag onto the timeline' : undefined}
            role="group"
            aria-label={m.name}
          >
            <span
              class="thumb {m.kind}"
              style:background-image={m.thumbs && m.status === 'ready' ? `url(${thumbsUrl(m.id)})` : undefined}
              aria-hidden="true"
            >
              {#if m.kind === 'audio'}♪{:else if m.status !== 'ready'}…{/if}
            </span>
            <span class="text">
              <span class="name">{m.name}</span>
              <span class="meta" class:bad={m.status === 'error'}>{detail(m)}</span>
            </span>
          </div>
          <div class="actions">
            <button
              type="button"
              class="mini"
              disabled={m.status !== 'ready'}
              aria-label="Add {m.name} at the playhead"
              title="Add at the playhead"
              onclick={() => editor.place(m, null, editor.playhead)}>+</button
            >
            <button
              type="button"
              class="mini"
              disabled={m.status === 'processing'}
              aria-label="Remove {m.name} from the bin"
              title="Remove from the bin"
              onclick={() => remove(m)}>×</button
            >
          </div>
        </li>
      {/each}
    </ul>
  {/if}
</section>

<style>
  .bin {
    display: flex;
    flex-direction: column;
    min-height: 0;
    background: var(--card);
    border-right: 1px solid var(--line);
  }
  .bin.dragging {
    outline: 2px dashed var(--accent);
    outline-offset: -6px;
  }
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 12px 6px;
  }
  h2 {
    margin: 0;
    font-size: 0.95rem;
  }
  .small {
    padding: 5px 12px;
    font-size: 0.85rem;
  }
  .filters {
    display: flex;
    gap: 2px;
    padding: 0 10px 8px;
    border-bottom: 1px solid var(--line);
  }
  .filters button {
    font: inherit;
    font-size: 0.78rem;
    color: var(--muted);
    background: none;
    border: 1px solid transparent;
    border-radius: 99px;
    padding: 2px 9px;
    cursor: pointer;
  }
  .filters button[aria-pressed='true'] {
    color: var(--ink);
    border-color: var(--line);
    background: var(--bg);
  }
  .hint {
    margin: 6px 12px;
  }
  .empty {
    padding: 18px 14px;
    color: var(--muted);
    font-size: 0.9rem;
    text-align: center;
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 6px;
    overflow-y: auto;
    flex: 1;
  }
  li {
    display: flex;
    align-items: center;
    gap: 4px;
    border-radius: 8px;
    padding: 4px;
  }
  li:hover {
    background: var(--bg);
  }
  .item {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
    flex: 1;
    cursor: grab;
  }
  .thumb {
    flex: none;
    width: 64px;
    height: 36px;
    border-radius: 5px;
    background: #000 0 0 / auto 36px no-repeat;
    display: grid;
    place-items: center;
    color: #fff;
    font-size: 1rem;
  }
  .thumb.audio {
    background: color-mix(in srgb, #3d7fb8 70%, var(--card));
  }
  .text {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }
  .name {
    font-size: 0.85rem;
    font-weight: 600;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .meta {
    font-size: 0.75rem;
    color: var(--muted);
  }
  .meta.bad {
    color: var(--bad);
  }
  .actions {
    display: flex;
    gap: 2px;
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
  .mini:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
</style>
