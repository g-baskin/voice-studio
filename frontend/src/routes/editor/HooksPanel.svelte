<script lang="ts">
  import * as api from '#lib/editor/api.ts';
  import type { Editor } from '#lib/editor/editor.svelte.ts';
  import { timecode } from '#lib/editor/timeline.ts';
  import type { HookCandidate, Media } from '#lib/editor/types.ts';

  let { editor, media, ontranscript }: { editor: Editor; media: Media; ontranscript?: () => void } = $props();

  let shortest = $state(15);
  let longest = $state(90);
  let count = $state(10);
  let hooks = $state<HookCandidate[] | null>(null);
  let rankedBy = $state<'structure' | 'ai'>('structure');
  let busy = $state(false);
  let error = $state('');

  const fps = $derived(editor.seq.fps);
  const tc = (t: number) => timecode(t, fps).replace(/^00:/, '');
  const data = $derived(editor.transcripts[media.id]);
  const ai = $derived(editor.speech?.ai ?? null);

  $effect(() => {
    if (!editor.speech) void editor.loadSpeechStatus();
  });
  $effect(() => {
    void editor.loadTranscript(media.id);
  });
  $effect(() => {
    void media.id;
    hooks = null;
    error = '';
  });

  const finite = (v: number, lo: number, hi: number, fallback: number) =>
    Number.isFinite(v) ? Math.min(hi, Math.max(lo, v)) : fallback;

  async function find(useAi: boolean) {
    busy = true;
    error = '';
    try {
      const lo = finite(shortest, 5, 600, 15);
      const reply = await api.findHooks(media.id, {
        min_len: lo,
        max_len: Math.max(lo, finite(longest, 5, 600, 90)),
        count: Math.round(finite(count, 1, 20, 10)),
        use_ai: useAi,
      });
      hooks = reply.hooks;
      rankedBy = reply.ranked_by;
    } catch (e) {
      error = e instanceof Error ? e.message : 'Could not find hooks.';
    } finally {
      busy = false;
    }
  }

  function subclip(h: HookCandidate) {
    editor.openMoment(media, h.start, h.end);
    editor.makeSubclip(h.text.split(/\s+/).slice(0, 6).join(' ').slice(0, 60));
  }
</script>

<h2>Hooks <span class="sub">ranked by structure and pace</span></h2>
<p class="hint">
  Candidate Shorts that start and end on whole sentences, scored on the opening line, pace, fillers and energy. They
  help you sort, not predict views.
</p>

{#if data === null}
  <p class="hint">Transcribe this file first.</p>
  <div class="actions">
    <button type="button" class="btn secondary small" onclick={() => ontranscript?.()}>Open Transcript</button>
  </div>
{:else if data}
  <div class="row3">
    <label>Shortest (s)<input type="number" min="5" max="600" step="1" bind:value={shortest} /></label>
    <label>Longest (s)<input type="number" min="5" max="600" step="1" bind:value={longest} /></label>
    <label>How many<input type="number" min="1" max="20" step="1" bind:value={count} /></label>
  </div>
  <div class="actions">
    <button type="button" class="btn small" disabled={busy} onclick={() => find(false)}>Find hooks</button>
    {#if ai && hooks?.length}
      <button
        type="button"
        class="btn secondary small"
        disabled={busy}
        title="Sends only the listed hook texts to {ai}"
        onclick={() => find(true)}>Rank with AI ({ai})</button
      >
    {/if}
  </div>
  {#if ai && hooks?.length}<p class="hint">Rank with AI sends only these hook texts to {ai}.</p>{/if}
  {#if error}<p class="bad" role="alert">{error}</p>{/if}

  {#if hooks}
    {#if hooks.length}
      <p class="meta">{rankedBy === 'ai' ? `Ordered by ${ai ?? 'the AI'}.` : 'Ordered by structure and pace.'}</p>
      <ol class="list" aria-label="Hooks">
        {#each hooks as h, i (h.id)}
          <li class="moment">
            <span class="score" title="Relative score within this file">{h.score}</span>
            <button
              type="button"
              class="link"
              aria-label="Hook {i + 1}: {tc(h.start)} to {tc(h.end)}, show in the source viewer"
              onclick={() => editor.openMoment(media, h.start, h.end)}>{tc(h.start)}–{tc(h.end)}</button
            >
            <q class="line">{h.text}</q>
            <span class="meta reasons">{(h.end - h.start).toFixed(0)} s · {h.reasons.join(', ')}</span>
            <div class="go">
              <button type="button" class="btn secondary small" onclick={() => editor.openMoment(media, h.start, h.end)}
                >Open in source</button
              >
              <button
                type="button"
                class="btn secondary small"
                onclick={() => editor.appendMoment(media, h.start, h.end)}>Add</button
              >
              <button type="button" class="btn secondary small" onclick={() => subclip(h)}>Add as subclip</button>
            </div>
          </li>
        {/each}
      </ol>
    {:else}
      <p class="hint">No whole-sentence passages fit those lengths. Try a wider range.</p>
    {/if}
  {/if}
{/if}

<style>
  .line,
  .reasons,
  .go {
    grid-column: 2;
  }
  .line {
    font-size: 0.8rem;
    overflow-wrap: anywhere;
  }
  .go {
    flex-wrap: wrap;
    margin-left: 0;
  }
</style>
