<script lang="ts">
  import type { Editor } from '#lib/editor/editor.svelte.ts';
  import { MARKER_HEX, timecode, type SilenceCut } from '#lib/editor/timeline.ts';
  import { MARKER_COLORS, type AnalysisKind, type MarkerColor, type Media } from '#lib/editor/types.ts';
  import CaptionsPanel from './CaptionsPanel.svelte';
  import HooksPanel from './HooksPanel.svelte';
  import TranscriptPanel from './TranscriptPanel.svelte';

  let { editor }: { editor: Editor } = $props();

  const TABS = [
    { id: 'transcript', label: 'Transcript' },
    { id: 'captions', label: 'Captions' },
    { id: 'hooks', label: 'Hooks' },
    { id: 'moments', label: 'Moments' },
    { id: 'silences', label: 'Silences' },
    { id: 'scenes', label: 'Scenes' },
    { id: 'markers', label: 'Markers' },
    { id: 'subclips', label: 'Subclips' },
  ] as const;
  type Tab = (typeof TABS)[number]['id'];
  const ANALYSED: Partial<Record<Tab, AnalysisKind>> = { moments: 'moments', silences: 'silence', scenes: 'scenes' };

  let tab = $state<Tab>('transcript');
  const TRANSCRIBED: Tab[] = ['transcript', 'hooks'];

  /** Open a tab from outside (the T key), moving focus to it. */
  export function show(id: Tab) {
    tab = id;
    tabEls[TABS.findIndex((t) => t.id === id)]?.focus();
  }

  // Hear a stretch of the file in the source viewer (used by the filler list's Listen buttons).
  function listen(m: Media, start: number, end: number) {
    editor.openMoment(m, Math.max(0, start - 0.5), end + 0.5);
  }
  let tabEls: HTMLButtonElement[] = $state([]);
  let chosen = $state<string | null>(null);

  // Moments, silences and scene parameters (bounds match the server's AnalysisRequest).
  let shortest = $state(15);
  let longest = $state(60);
  let count = $state(10);
  let noiseDb = $state(-40);
  let minSilence = $state(0.5);
  let padding = $state(0.15);
  let least = $state(0.2);
  let threshold = $state(0.3);
  let skipped = $state<string[]>([]);

  const fps = $derived(editor.seq.fps);
  const tc = (t: number) => timecode(t, fps);
  // Hours are rarely needed in this narrow panel.
  const short = (t: number) => tc(t).replace(/^00:/, '');
  const analysable = $derived(editor.media.filter((m) => m.status === 'ready' && m.kind !== 'image' && m.duration));
  // The file to analyse: the one picked here, else the source viewer's, else the selected clip's, else the first.
  const media = $derived.by((): Media | null => {
    const ids = [chosen, editor.source?.media, editor.selected[0]?.media];
    for (const id of ids) {
      const m = id ? analysable.find((x) => x.id === id) : undefined;
      if (m) return m;
    }
    return analysable[0] ?? null;
  });
  const kind = $derived(ANALYSED[tab] ?? null);
  const job = $derived(media && kind ? editor.analysisFor(media.id, kind) : null);
  const result = $derived(job?.status === 'done' ? job.result : null);
  const onTimeline = $derived(media ? editor.clipsOf(media.id).length : 0);
  const usable = $derived(!media ? false : kind === 'scenes' ? media.has_video : media.has_audio);

  const spans = $derived(
    media && result?.kind === 'silence' ? editor.silenceSpans(media.id, result.ranges, padding, least) : [],
  );
  const spanKey = (s: SilenceCut) => `${s[0].toFixed(3)}-${s[2].join(',')}`;
  const picked = $derived(spans.filter((s) => !skipped.includes(spanKey(s))));
  const pickedSeconds = $derived(picked.reduce((sum, [a, b]) => sum + b - a, 0));
  const sceneHits = $derived(media && result?.kind === 'scenes' ? editor.sceneTimes(media.id, result.times) : []);

  const finite = (v: number, lo: number, hi: number, fallback: number) =>
    Number.isFinite(v) ? Math.min(hi, Math.max(lo, v)) : fallback;

  function run() {
    if (!media || !kind) return;
    if (kind === 'moments') {
      const lo = finite(shortest, 1, 600, 15);
      void editor.analyse(media, kind, {
        min_length: lo,
        max_length: Math.max(lo, finite(longest, 1, 600, 60)),
        count: Math.round(finite(count, 1, 30, 10)),
      });
    } else if (kind === 'silence') {
      skipped = [];
      void editor.analyse(media, kind, {
        noise_db: finite(noiseDb, -80, -10, -40),
        min_seconds: finite(minSilence, 0.1, 10, 0.5),
      });
    } else void editor.analyse(media, kind, { threshold: finite(threshold, 0.05, 0.95, 0.3) });
  }

  function toggle(span: SilenceCut) {
    const key = spanKey(span);
    skipped = skipped.includes(key) ? skipped.filter((k) => k !== key) : [...skipped, key];
  }

  function tabKey(e: KeyboardEvent, i: number) {
    const step = { ArrowRight: 1, ArrowLeft: -1, Home: -i, End: TABS.length - 1 - i }[e.key];
    if (step === undefined) return;
    e.preventDefault();
    const next = (i + step + TABS.length) % TABS.length;
    tab = TABS[next].id;
    tabEls[next]?.focus();
  }

  function seekSource(t: number) {
    if (!media) return;
    if (editor.source?.media !== media.id) editor.loadSource(media);
    editor.seekSource(t);
  }
</script>

<aside class="clip-panel" aria-label="Clip tools">
  <div class="tabs" role="tablist" aria-label="Clip tools">
    {#each TABS as t, i (t.id)}
      <button
        type="button"
        role="tab"
        id="clip-tab-{t.id}"
        aria-selected={tab === t.id}
        aria-controls="clip-panel-body"
        tabindex={tab === t.id ? 0 : -1}
        bind:this={tabEls[i]}
        onclick={() => (tab = t.id)}
        onkeydown={(e) => tabKey(e, i)}>{t.label}</button
      >
    {/each}
  </div>

  <div class="body" id="clip-panel-body" role="tabpanel" aria-labelledby="clip-tab-{tab}">
    {#if TRANSCRIBED.includes(tab)}
      {#if !analysable.length}
        <p class="hint">Import a video or audio file to transcribe it.</p>
      {:else if media}
        <label
          >File
          <select value={media.id} onchange={(e) => (chosen = (e.currentTarget as HTMLSelectElement).value)}>
            {#each analysable as m (m.id)}<option value={m.id}>{m.name}</option>{/each}
          </select>
        </label>
        {#if tab === 'transcript'}
          <TranscriptPanel {editor} {media} onlisten={listen} />
        {:else}
          <HooksPanel {editor} {media} ontranscript={() => show('transcript')} />
        {/if}
      {/if}
    {:else if tab === 'captions'}
      <CaptionsPanel {editor} />
    {:else if kind}
      {#if !analysable.length}
        <p class="hint">Import a video or audio file to analyse it.</p>
      {:else}
        <label
          >File
          <select value={media?.id} onchange={(e) => (chosen = (e.currentTarget as HTMLSelectElement).value)}>
            {#each analysable as m (m.id)}<option value={m.id}>{m.name}</option>{/each}
          </select>
        </label>

        {#if tab === 'moments'}
          <h2>Moments <span class="sub">ranked by energy and pace</span></h2>
          <p class="hint">
            Scores compare parts of this file by loudness, pauses and cuts. They help you sort, not predict views.
          </p>
          <div class="row3">
            <label>Shortest (s)<input type="number" min="1" max="600" step="1" bind:value={shortest} /></label>
            <label>Longest (s)<input type="number" min="1" max="600" step="1" bind:value={longest} /></label>
            <label>How many<input type="number" min="1" max="30" step="1" bind:value={count} /></label>
          </div>
        {:else if tab === 'silences'}
          <h2>Silences</h2>
          <p class="hint">Find pauses, untick any to keep, then remove the rest from this file's clips in one step.</p>
          <div class="row2">
            <label>Quieter than (dB)<input type="number" min="-80" max="-10" step="1" bind:value={noiseDb} /></label>
            <label>For at least (s)<input type="number" min="0.1" max="10" step="0.1" bind:value={minSilence} /></label>
            <label>Keep each side (s)<input type="number" min="0" max="2" step="0.05" bind:value={padding} /></label>
            <label>Shortest cut (s)<input type="number" min="0" max="10" step="0.05" bind:value={least} /></label>
          </div>
        {:else}
          <h2>Scene changes</h2>
          <p class="hint">Find picture cuts, then mark them or split this file's clips there.</p>
          <label
            >Sensitivity (lower finds more)
            <input type="number" min="0.05" max="0.95" step="0.05" bind:value={threshold} /></label
          >
        {/if}

        <div class="actions">
          {#if job?.status === 'running'}
            <progress max="1" value={job.progress} aria-label="Analysis progress"></progress>
            <button
              type="button"
              class="btn secondary small"
              onclick={() => media && kind && editor.cancelAnalysis(media.id, kind)}>Cancel</button
            >
          {:else}
            <button type="button" class="btn small" disabled={!usable} onclick={run}
              >{tab === 'moments'
                ? 'Find moments'
                : tab === 'silences'
                  ? 'Find silences'
                  : 'Find scene changes'}</button
            >
            {#if media && !usable}<span class="hint"
                >{kind === 'scenes' ? 'This file has no picture.' : 'This file has no sound.'}</span
              >{/if}
          {/if}
        </div>
        {#if job?.status === 'error'}<p class="bad" role="alert">{job.error}</p>{/if}
        {#if job?.status === 'cancelled'}<p class="hint">Cancelled.</p>{/if}

        {#if result?.kind === 'moments' && media}
          {#if result.moments.length}
            <ol class="list" aria-label="Moments">
              {#each result.moments as m, i (m.start)}
                <li class="moment">
                  <span class="score" title="Relative score within this file">{m.score}</span>
                  <button
                    type="button"
                    class="link"
                    aria-label="Moment {i + 1}: {tc(m.start)} to {tc(m.end)}, show in the source viewer"
                    onclick={() => seekSource(m.start)}>{short(m.start)}–{short(m.end)}</button
                  >
                  <span class="meta reasons">{(m.end - m.start).toFixed(0)} s · {m.reasons.join(', ')}</span>
                  <div class="go">
                    <button
                      type="button"
                      class="btn secondary small"
                      onclick={() => editor.openMoment(media, m.start, m.end)}>Open in source</button
                    >
                    <button
                      type="button"
                      class="btn secondary small"
                      onclick={() => editor.appendMoment(media, m.start, m.end)}>Add</button
                    >
                  </div>
                </li>
              {/each}
            </ol>
          {:else}
            <p class="hint">This file is shorter than the shortest moment.</p>
          {/if}
        {:else if result?.kind === 'silence' && media}
          <p class="meta">
            {result.ranges.length} silence{result.ranges.length === 1 ? '' : 's'} in the file;
            {spans.length} inside its clips on the timeline.
          </p>
          {#if !onTimeline}
            <p class="hint">Put this file on the timeline first: silences are cut from its clips.</p>
          {:else if spans.length}
            <ul class="list" aria-label="Silences to remove">
              {#each spans as s (spanKey(s))}
                <li>
                  <label class="check">
                    <input type="checkbox" checked={!skipped.includes(spanKey(s))} onchange={() => toggle(s)} />
                    {tc(s[0])}–{tc(s[1])}
                    <span class="meta">{(s[1] - s[0]).toFixed(2)} s</span>
                  </label>
                  <button
                    type="button"
                    class="link"
                    aria-label="Go to {tc(s[0])}"
                    onclick={() => (editor.playhead = s[0])}>Go</button
                  >
                </li>
              {/each}
            </ul>
            <button
              type="button"
              class="btn small"
              disabled={!picked.length}
              onclick={() => media && editor.removeSilences(picked)}
              >Remove {picked.length} silence{picked.length === 1 ? '' : 's'} ({pickedSeconds.toFixed(1)} s)</button
            >
          {/if}
        {:else if result?.kind === 'scenes' && media}
          <p class="meta">
            {result.times.length} scene change{result.times.length === 1 ? '' : 's'} in the file;
            {sceneHits.length} inside its clips on the timeline.
          </p>
          {#if result.times.length}
            <ul class="list chips" aria-label="Scene changes">
              {#each result.times as t (t)}
                <li><button type="button" class="link" onclick={() => seekSource(t)}>{tc(t)}</button></li>
              {/each}
            </ul>
          {/if}
          <div class="actions">
            <button
              type="button"
              class="btn secondary small"
              disabled={!sceneHits.length}
              onclick={() => media && editor.scenesToMarkers(media.id, result.times)}>Add as markers</button
            >
            <button
              type="button"
              class="btn secondary small"
              disabled={!sceneHits.length}
              onclick={() => media && editor.scenesToSplits(media.id, result.times)}>Split clips there</button
            >
          </div>
        {/if}
      {/if}
    {:else if tab === 'markers'}
      <h2>Markers</h2>
      <div class="actions">
        <button type="button" class="btn secondary small" onclick={() => editor.addMarker(editor.playhead)}
          >Add at playhead (M)</button
        >
      </div>
      {#if editor.seq.markers.length}
        <ul class="list" aria-label="Markers">
          {#each editor.seq.markers as mk, i (`${mk.time}:${i}`)}
            <li class="marker">
              <select
                class="swatch"
                style:--swatch={MARKER_HEX[mk.color]}
                value={mk.color}
                aria-label="Colour of marker {i + 1}"
                onchange={(e) =>
                  editor.updateMarker(i, { color: (e.currentTarget as HTMLSelectElement).value as MarkerColor })}
              >
                {#each MARKER_COLORS as c (c)}<option value={c}>{c}</option>{/each}
              </select>
              <button type="button" class="link tc" onclick={() => (editor.playhead = mk.time)}>{tc(mk.time)}</button>
              <input
                type="text"
                maxlength="60"
                value={mk.label}
                placeholder="Label"
                aria-label="Label of marker {i + 1}"
                onchange={(e) => editor.updateMarker(i, { label: (e.currentTarget as HTMLInputElement).value })}
              />
              <button
                type="button"
                class="x"
                aria-label="Delete marker at {tc(mk.time)}"
                onclick={() => editor.removeMarker(i)}>×</button
              >
            </li>
          {/each}
        </ul>
      {:else}
        <p class="hint">No markers yet. Press M to mark the playhead.</p>
      {/if}
    {:else}
      <h2>Subclips</h2>
      <div class="actions">
        <button type="button" class="btn secondary small" disabled={!editor.source} onclick={() => editor.makeSubclip()}
          >From source In–Out (⌘/Ctrl U)</button
        >
      </div>
      {#if editor.seq.subclips.length}
        <ul class="list" aria-label="Subclips">
          {#each editor.seq.subclips as sub (sub.id)}
            {@const m = editor.mediaById.get(sub.media)}
            <li class="subclip">
              <input
                type="text"
                maxlength="60"
                value={sub.name}
                aria-label="Name of subclip {sub.name}"
                onchange={(e) => editor.renameSubclip(sub.id, (e.currentTarget as HTMLInputElement).value)}
              />
              <span class="meta"
                >{m?.name ?? 'Missing file'} · {tc(sub.source_in)}–{tc(sub.source_out)} · {(
                  sub.source_out - sub.source_in
                ).toFixed(1)} s</span
              >
              <div class="go">
                <button
                  type="button"
                  class="btn secondary small"
                  disabled={!m}
                  onclick={() => m && editor.loadSource(m, sub)}>Open</button
                >
                <button
                  type="button"
                  class="x"
                  aria-label="Delete subclip {sub.name}"
                  onclick={() => editor.removeSubclip(sub.id)}>×</button
                >
              </div>
            </li>
          {/each}
        </ul>
      {:else}
        <p class="hint">Mark In and Out in the source viewer, then save the range as a subclip.</p>
      {/if}
    {/if}
  </div>
</aside>

<style>
  .clip-panel {
    display: flex;
    flex-direction: column;
    min-height: 0;
    min-width: 0;
    background: var(--card);
    border-left: 1px solid var(--line);
    font-size: 0.85rem;
  }
  .tabs {
    /* A scrolling strip would otherwise shrink to nothing when the body below is tall. */
    flex: none;
    display: flex;
    gap: 2px;
    padding: 6px 8px 0;
    overflow-x: auto;
    scrollbar-width: thin;
    border-bottom: 1px solid var(--line);
  }
  [role='tab'] {
    flex: none;
    padding: 5px 7px;
    font: inherit;
    font-size: 0.78rem;
    font-weight: 600;
    color: var(--muted);
    background: none;
    border: 0;
    border-bottom: 2px solid transparent;
    cursor: pointer;
  }
  [role='tab'][aria-selected='true'] {
    color: var(--ink);
    border-bottom-color: var(--accent);
  }
  .body {
    display: flex;
    flex-direction: column;
    gap: 8px;
    min-height: 0;
    overflow-y: auto;
    padding: 10px 12px 14px;
  }
  .body :global(h2) {
    margin: 0;
    font-size: 0.92rem;
  }
  .body :global(.sub) {
    font-weight: 500;
    font-size: 0.78rem;
    color: var(--muted);
  }
  .body :global(label) {
    display: flex;
    flex-direction: column;
    gap: 3px;
    font-weight: 600;
    font-size: 0.78rem;
    min-width: 0;
  }
  .body :global(label.check) {
    flex: 1;
    flex-direction: row;
    align-items: center;
    gap: 6px;
    font-weight: 500;
    font-variant-numeric: tabular-nums;
  }
  .body :global(input[type='number']),
  .body :global(input[type='text']),
  .body :global(select) {
    width: 100%;
    min-width: 0;
    box-sizing: border-box;
    padding: 4px 6px;
    font: inherit;
    font-size: 0.8rem;
    color: var(--ink);
    background: var(--bg);
    border: 1px solid var(--line);
    border-radius: 5px;
  }
  .body :global(.row2),
  .body :global(.row3) {
    display: grid;
    gap: 6px;
  }
  .body :global(.row2) {
    grid-template-columns: 1fr 1fr;
  }
  .body :global(.row3) {
    grid-template-columns: 1fr 1fr 1fr;
  }
  .body :global(.actions) {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
  }
  .body :global(progress) {
    flex: 1;
    min-width: 0;
    accent-color: var(--accent);
  }
  .body :global(.hint),
  .body :global(.meta) {
    margin: 0;
    font-size: 0.76rem;
    color: var(--muted);
  }
  .body :global(.bad) {
    margin: 0;
    font-size: 0.8rem;
    color: var(--bad);
  }
  .body :global(.list) {
    display: flex;
    flex-direction: column;
    gap: 4px;
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .body :global(.list > li) {
    display: flex;
    align-items: center;
    gap: 6px;
    min-width: 0;
    padding: 4px 0;
    border-bottom: 1px solid var(--line);
  }
  .body :global(.list.chips) {
    flex-direction: row;
    flex-wrap: wrap;
  }
  .body :global(.list.chips > li) {
    border: 0;
    padding: 0 4px 0 0;
  }
  .body :global(.list > li.moment) {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    align-items: center;
    gap: 4px 8px;
  }
  .moment .reasons,
  .moment .go {
    grid-column: 2;
  }
  .moment .go {
    margin-left: 0;
  }
  .subclip {
    flex-wrap: wrap;
  }
  .body :global(.score) {
    flex: none;
    width: 2.2em;
    padding: 3px 0;
    text-align: center;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    color: var(--accent-ink);
    background: var(--accent);
    border-radius: 5px;
  }
  .body :global(.go) {
    display: flex;
    gap: 4px;
    margin-left: auto;
  }
  .subclip input {
    flex: 1 1 100%;
  }
  .marker input {
    flex: 1;
  }
  .body :global(.link) {
    padding: 0;
    font: inherit;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    text-align: left;
    color: var(--accent);
    background: none;
    border: 0;
    cursor: pointer;
  }
  .body :global(.link:hover) {
    text-decoration: underline;
  }
  .tc {
    flex: none;
  }
  .body :global(.x) {
    flex: none;
    width: 24px;
    height: 24px;
    padding: 0;
    font: inherit;
    font-weight: 700;
    color: var(--muted);
    background: none;
    border: 1px solid var(--line);
    border-radius: 5px;
    cursor: pointer;
  }
  .swatch {
    flex: none;
    width: 4.6em;
    border-left: 6px solid var(--swatch);
  }
  .body :global(.small) {
    padding: 4px 10px;
    font-size: 0.8rem;
  }
</style>
