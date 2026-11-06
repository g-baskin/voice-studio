<script lang="ts">
  import { tick } from 'svelte';
  import type { Editor } from '#lib/editor/editor.svelte.ts';
  import { timecode } from '#lib/editor/timeline.ts';
  import type { FillerCandidate, Media, Word } from '#lib/editor/types.ts';

  let {
    editor,
    media,
    onlisten,
  }: { editor: Editor; media: Media; onlisten?: (media: Media, start: number, end: number) => void } = $props();

  const PAGE = 400;
  // Settings the server uses to find sounding gaps between words (transcript.SILENCE_PARAMS).
  const GAP_SILENCE = { noise_db: -35, min_seconds: 0.2 };

  let anchor = $state<number | null>(null);
  let focus = $state<number | null>(null);
  let editing = $state<number | null>(null);
  let draft = $state('');
  let first = $state(0);
  let ticked = $state<string[]>([]);
  let longer = $state(0.6);
  let keep = $state(0.25);
  let reloadedFor = $state('');

  const fps = $derived(editor.seq.fps);
  const tc = (t: number) => timecode(t, fps).replace(/^00:/, '');
  const status = $derived(editor.speech);
  const data = $derived(editor.transcripts[media.id]);
  const words = $derived(data?.words ?? []);
  const job = $derived(editor.transcriptions[media.id]);
  const running = $derived(job?.status === 'running');
  const lo = $derived(anchor === null || focus === null ? -1 : Math.min(anchor, focus));
  const hi = $derived(anchor === null || focus === null ? -1 : Math.max(anchor, focus));
  const chosen = $derived(lo < 0 ? [] : Array.from({ length: hi - lo + 1 }, (_, k) => lo + k));
  const shown = $derived(words.slice(first, first + PAGE));
  // The one word in the list that Tab reaches; arrow keys move it.
  const current = $derived(focus !== null && focus >= first && focus < first + PAGE ? focus : first);
  let list = $state<HTMLDivElement>();
  const clips = $derived(editor.seq.clips.filter((c) => c.media === media.id));
  const silence = $derived(editor.analysisFor(media.id, 'silence'));
  const fillerKey = (f: FillerCandidate) => (f.kind === 'word' ? `w${f.index}` : `g${f.t0}`);
  const fillers = $derived(data?.fillers ?? []);
  const picked = $derived(fillers.filter((f) => ticked.includes(fillerKey(f))));

  $effect(() => {
    if (!editor.speech) void editor.loadSpeechStatus();
  });
  $effect(() => {
    void editor.loadTranscript(media.id);
  });
  // A new file starts with nothing selected.
  $effect(() => {
    void media.id;
    anchor = focus = editing = null;
    first = 0;
    ticked = [];
  });
  // Once the silence check for possible fillers finishes, fetch the gap picks it makes possible.
  $effect(() => {
    if (silence?.status === 'done' && data?.silence && reloadedFor !== silence.id) {
      reloadedFor = silence.id;
      void editor.loadTranscript(media.id, true);
    }
  });

  const onTimeline = (w: Word) =>
    clips.some((c) => (w[0] + w[1]) / 2 >= c.source_in && (w[0] + w[1]) / 2 < c.source_out);

  function seek(t: number) {
    if (editor.source?.media !== media.id) editor.loadSource(media);
    editor.seekSource(t);
  }

  function pick(i: number, extend: boolean) {
    if (extend && anchor !== null) focus = i;
    else anchor = focus = i;
    seek(words[i][0]);
  }

  async function moveTo(i: number, extend: boolean) {
    const j = Math.max(0, Math.min(words.length - 1, i));
    first = Math.floor(j / PAGE) * PAGE;
    pick(j, extend);
    await tick();
    list?.querySelector<HTMLButtonElement>(`[data-word="${j}"]`)?.focus();
  }

  const focusInput = (node: HTMLInputElement) => {
    node.focus();
    node.select();
  };

  function startEdit(i: number) {
    editing = i;
    draft = words[i][2];
  }

  async function finishEdit(save: boolean) {
    const i = editing;
    editing = null;
    if (!save || i === null) return;
    const text = draft.trim();
    if (!text || text === words[i][2]) return;
    const next = words.map((w, k): Word => (k === i ? [w[0], w[1], text] : w));
    await editor.saveWords(media.id, next);
  }

  function remove() {
    if (!chosen.length) return;
    editor.removeWords(media.id, chosen);
    anchor = focus = null;
  }

  function listKey(e: KeyboardEvent) {
    if (editing !== null) return;
    if ((e.key === 'Delete' || e.key === 'Backspace') && chosen.length) {
      e.preventDefault();
      e.stopPropagation();
      remove();
    } else if (e.key === 'Escape' && chosen.length) {
      e.stopPropagation();
      anchor = focus = null;
    } else if (!words.length || e.metaKey || e.ctrlKey || e.altKey) {
      return;
    } else if (e.key === 'F2') {
      e.preventDefault();
      e.stopPropagation();
      startEdit(current);
    } else {
      const to = { ArrowLeft: current - 1, ArrowRight: current + 1, Home: 0, End: words.length - 1 }[e.key];
      if (to === undefined) return;
      e.preventDefault();
      e.stopPropagation();
      void moveTo(to, e.shiftKey);
    }
  }

  function run() {
    if (data?.edited && !confirm('Transcribe again and replace your edited words?')) return;
    void editor.transcribe(media, !!data?.edited);
  }

  function toggleFiller(f: FillerCandidate) {
    const key = fillerKey(f);
    ticked = ticked.includes(key) ? ticked.filter((k) => k !== key) : [...ticked, key];
  }

  const fillerSpan = (f: FillerCandidate): [number, number] =>
    f.kind === 'gap' ? [f.t0, f.t1] : [words[f.index]?.[0] ?? 0, words[f.index]?.[1] ?? 0];

  function removeFillers() {
    editor.removeFillers(media.id, picked);
    ticked = [];
  }

  const finite = (v: number, lo: number, hi: number, fallback: number) =>
    Number.isFinite(v) ? Math.min(hi, Math.max(lo, v)) : fallback;
</script>

<h2>Transcript <span class="sub">on this computer, English</span></h2>

{#if status && !status.installed && !data}
  <div class="setup" role="note">
    <p><strong>Speech-to-text is not installed yet.</strong></p>
    <p class="hint">
      It runs entirely on this computer and needs a one-time download of about 660 MB (keep 1.4 GB free). In the app
      folder, run:
    </p>
    <code>scripts/setup_speech_model.sh</code>
    <p class="hint">Then reload this page. A one-hour file takes roughly 10 to 20 minutes to transcribe.</p>
    <p class="hint">
      Model: NVIDIA Parakeet TDT 0.6B v2, licensed
      <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noreferrer">CC-BY-4.0</a>.
    </p>
  </div>
{:else}
  <div class="actions">
    {#if running}
      <progress max="1" value={job?.progress ?? 0} aria-label="Transcription progress"></progress>
      <button type="button" class="btn secondary small" onclick={() => editor.cancelTranscribe(media.id)}>Cancel</button
      >
    {:else}
      <button type="button" class="btn small" disabled={!media.has_audio || !status?.installed} onclick={run}
        >{data ? 'Transcribe again' : 'Transcribe'}</button
      >
      {#if !media.has_audio}<span class="hint">This file has no sound.</span>{/if}
    {/if}
  </div>
  {#if job?.status === 'error'}<p class="bad" role="alert">{job.error}</p>{/if}
  {#if job?.status === 'cancelled'}<p class="hint">Cancelled.</p>{/if}
{/if}

{#if data}
  <p class="meta">
    {words.length} words{data.edited ? ' · edited' : ''}. Click a word or use the arrow keys to find it, Shift-click or
    Shift+arrow to select a run, double-click or F2 to fix its text, Delete to cut the selection from the timeline.
  </p>
  {#if words.length > PAGE}
    <div class="actions pager">
      <button type="button" class="btn secondary small" disabled={first === 0} onclick={() => (first -= PAGE)}
        >Earlier</button
      >
      <span class="meta">{tc(words[first][0])}–{tc(words[Math.min(words.length, first + PAGE) - 1][1])}</span>
      <button
        type="button"
        class="btn secondary small"
        disabled={first + PAGE >= words.length}
        onclick={() => (first += PAGE)}>Later</button
      >
    </div>
  {/if}
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <div class="words" role="group" aria-label="Transcript words" tabindex="-1" bind:this={list} onkeydown={listKey}>
    {#each shown as w, k (first + k)}
      {@const i = first + k}
      {#if editing === i}
        <input
          class="edit"
          type="text"
          maxlength="48"
          aria-label="Fix the word"
          use:focusInput
          bind:value={draft}
          onblur={() => finishEdit(true)}
          onkeydown={(e) => {
            if (e.key === 'Enter') finishEdit(true);
            else if (e.key === 'Escape') finishEdit(false);
            e.stopPropagation();
          }}
        />
      {:else}
        <button
          type="button"
          class="word"
          class:on={i >= lo && i <= hi}
          class:cut={!onTimeline(w)}
          aria-pressed={i >= lo && i <= hi}
          aria-keyshortcuts="F2"
          tabindex={i === current ? 0 : -1}
          data-word={i}
          title="{tc(w[0])}{onTimeline(w) ? '' : ' · not on the timeline'}"
          onclick={(e) => pick(i, e.shiftKey)}
          ondblclick={() => startEdit(i)}>{w[2]}</button
        >
      {/if}
    {/each}
  </div>
  <div class="actions">
    <button type="button" class="btn secondary small" disabled={!chosen.length} onclick={remove}
      >Cut {chosen.length || ''} word{chosen.length === 1 ? '' : 's'} from the timeline</button
    >
  </div>

  <h3>Clean up</h3>
  {#if !clips.length}
    <p class="hint">Put this file on the timeline first: cleanup cuts its clips.</p>
  {/if}
  <label class="check"
    ><input
      type="checkbox"
      bind:checked={editor.extraFillers}
      onchange={() => editor.loadTranscript(media.id, true)}
    />Also list “like”, “you know” and “I mean”</label
  >
  {#if data.silence}
    <p class="hint">
      The model often leaves out “um” and “uh”. Check for sound between words to list those possible fillers too.
    </p>
    <div class="actions">
      <button
        type="button"
        class="btn secondary small"
        disabled={silence?.status === 'running'}
        onclick={() => editor.analyse(media, 'silence', GAP_SILENCE)}
        >{silence?.status === 'running' ? 'Checking...' : 'Find possible fillers'}</button
      >
    </div>
  {/if}
  {#if fillers.length}
    <ul class="list" aria-label="Fillers">
      {#each fillers as f (fillerKey(f))}
        {@const [a, b] = fillerSpan(f)}
        <li>
          <label class="check">
            <input type="checkbox" checked={ticked.includes(fillerKey(f))} onchange={() => toggleFiller(f)} />
            {f.kind === 'word' ? `“${words[f.index]?.[2] ?? ''}”` : 'Possible filler'}
            <span class="meta">{tc(a)} · {(b - a).toFixed(2)} s</span>
          </label>
          <button type="button" class="link" aria-label="Listen at {tc(a)}" onclick={() => onlisten?.(media, a, b)}
            >Listen</button
          >
        </li>
      {/each}
    </ul>
    <button type="button" class="btn small" disabled={!picked.length} onclick={removeFillers}
      >Remove {picked.length} filler{picked.length === 1 ? '' : 's'}</button
    >
  {:else}
    <p class="hint">No fillers found{data.silence ? ' among the words' : ''}.</p>
  {/if}

  <div class="row2">
    <label>Pauses longer than (s)<input type="number" min="0.2" max="5" step="0.05" bind:value={longer} /></label>
    <label>Shorten to (s)<input type="number" min="0" max="2" step="0.05" bind:value={keep} /></label>
  </div>
  <div class="actions">
    <button
      type="button"
      class="btn secondary small"
      disabled={!clips.length}
      onclick={() => editor.shortenPauses(media.id, finite(longer, 0.2, 5, 0.6), finite(keep, 0, 2, 0.25))}
      >Shorten pauses</button
    >
  </div>
{/if}

<style>
  .setup {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 10px;
    border: 1px solid var(--line);
    border-radius: 6px;
    background: var(--bg);
  }
  .setup p {
    margin: 0;
  }
  code {
    padding: 4px 6px;
    font-size: 0.78rem;
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 4px;
    user-select: all;
    overflow-wrap: anywhere;
  }
  h3 {
    margin: 6px 0 0;
    font-size: 0.85rem;
  }
  .words {
    display: flex;
    flex-wrap: wrap;
    gap: 2px;
    max-height: 260px;
    overflow-y: auto;
    padding: 6px;
    background: var(--bg);
    border: 1px solid var(--line);
    border-radius: 6px;
    line-height: 1.5;
  }
  .word {
    padding: 0 3px;
    font: inherit;
    color: var(--ink);
    background: none;
    border: 1px solid transparent;
    border-radius: 3px;
    cursor: pointer;
  }
  .word:hover {
    border-color: var(--line);
  }
  .word.on {
    color: var(--accent-ink);
    background: var(--accent);
  }
  .word.cut {
    color: var(--muted);
    text-decoration: line-through;
  }
  .edit {
    width: 9em;
  }
  .pager {
    justify-content: space-between;
  }
</style>
