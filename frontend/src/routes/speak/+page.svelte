<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { request } from '#lib/api.ts';
  import { PRODUCT } from '#lib/nav.ts';
  import {
    castFor,
    SAMPLE,
    speakersIn,
    STATUS_LABEL,
    type ChunkView,
    type DirectionInfo,
    type JobView,
    type Voice,
  } from '#lib/shark.ts';

  let script = $state(SAMPLE);
  let voices = $state<Voice[]>([]);
  let directions = $state<DirectionInfo[]>([]);
  let voice = $state('af_heart');
  let chosen = $state<Record<string, string>>({});
  let job = $state<JobView | null>(null);
  let status = $state('');
  let busy = $state(false);
  let notes = $state<Record<number, string>>({});
  let feedback = $state<Record<number, string>>({});
  let player: HTMLAudioElement | undefined = $state();
  let editor: HTMLTextAreaElement | undefined = $state();
  let playing = $state<string | null>(null);
  let timer: ReturnType<typeof setTimeout> | undefined;

  const cast = $derived(castFor(script, chosen, voices));
  const speakers = $derived(speakersIn(script));
  const ready = $derived(job?.chunks.filter((c) => c.state === 'ready').length ?? 0);
  const running = $derived(job?.status === 'running');

  onMount(async () => {
    try {
      const [v, d] = await Promise.all([
        request('/api/voices').then((r) => r.json() as Promise<{ catalog: Voice[] }>),
        request('/api/shark/directions').then((r) => r.json() as Promise<{ directions: DirectionInfo[] }>),
      ]);
      voices = v.catalog;
      directions = d.directions;
    } catch (error) {
      status = error instanceof Error ? error.message : 'Could not load voices.';
    }
  });

  onDestroy(() => clearTimeout(timer));

  function insert(tag: string) {
    const at = editor?.selectionStart ?? script.length;
    const before = script.slice(0, at);
    const piece = `${before && !/\s$/.test(before) ? ' ' : ''}[${tag}] `;
    script = before + piece + script.slice(at);
    requestAnimationFrame(() => {
      editor?.focus();
      editor?.setSelectionRange(at + piece.length, at + piece.length);
    });
  }

  function audioUrl(chunk: ChunkView, version = chunk.selected ?? 0) {
    return `/api/shark/jobs/${job?.job}/chunks/${chunk.index}/${version}.wav`;
  }

  function play(url: string) {
    if (!player) return;
    player.src = url;
    playing = url;
    void player.play().catch(() => (playing = null));
  }

  async function poll(id: string) {
    try {
      job = (await (await request(`/api/shark/jobs/${id}`)).json()) as JobView;
      if (job.status === 'running') timer = setTimeout(() => void poll(id), 400);
      else
        status =
          job.status === 'done'
            ? `Performance ready: ${ready} of ${job.chunks.length} chunks.`
            : (job.error ?? 'Stopped.');
    } catch (error) {
      status = error instanceof Error ? error.message : 'Lost track of the performance.';
    }
  }

  async function perform(event: SubmitEvent) {
    event.preventDefault();
    busy = true;
    status = 'Performing. Chunks play as soon as each is ready.';
    clearTimeout(timer);
    try {
      const body = JSON.stringify({ script, voice, cast });
      const { job: id } = (await (
        await request('/api/shark/perform', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body })
      ).json()) as { job: string };
      notes = {};
      feedback = {};
      await poll(id);
    } catch (error) {
      status = error instanceof Error ? error.message : 'Could not start.';
    } finally {
      busy = false;
    }
  }

  async function cancel() {
    if (job) await request(`/api/shark/jobs/${job.job}/cancel`, { method: 'POST' }).catch(() => undefined);
  }

  async function revise(chunk: ChunkView, retake: boolean) {
    if (!job) return;
    const instruction = retake ? '' : (notes[chunk.index] ?? '').trim();
    feedback[chunk.index] = retake ? 'Recording another take…' : 'Applying your note…';
    try {
      const res = (await (
        await request(`/api/shark/jobs/${job.job}/chunks/${chunk.index}/revise`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ instruction, retake }),
        })
      ).json()) as { understood: string[]; unused: string[]; chunk: ChunkView };
      job.chunks[chunk.index] = res.chunk;
      const heard = res.understood.length ? `Understood: ${res.understood.join('; ')}.` : 'New take recorded.';
      const missed = res.unused.length ? ` Ignored: ${res.unused.join(', ')}.` : '';
      feedback[chunk.index] = heard + missed;
      play(audioUrl(res.chunk));
    } catch (error) {
      feedback[chunk.index] = error instanceof Error ? error.message : 'Revision failed.';
    }
  }

  async function select(chunk: ChunkView, version: number) {
    if (!job) return;
    try {
      const res = (await (
        await request(`/api/shark/jobs/${job.job}/chunks/${chunk.index}/select`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ version }),
        })
      ).json()) as ChunkView;
      job.chunks[chunk.index] = res;
    } catch (error) {
      feedback[chunk.index] = error instanceof Error ? error.message : 'Could not choose that version.';
    }
  }
</script>

<svelte:head><title>Speak · {PRODUCT}</title></svelte:head>

<h1>Speak</h1>
<p class="lede">
  Write a scene, direct it with tags like <code>[whisper]</code> or <code>[excited]</code>, then hear it chunk by chunk.
  Retake or revise any chunk in plain words. Everything runs on this computer.
</p>

<form class="card" onsubmit={perform} aria-labelledby="script-h">
  <h2 id="script-h">Script</h2>
  <p class="hint">
    Start a line with <code>Name:</code> for each speaker. A direction lasts until the next one.
  </p>
  <label for="script">Scene</label>
  <textarea id="script" bind:this={editor} bind:value={script} rows="8" maxlength="20000" required></textarea>
  {#if directions.length}
    <div class="tags" role="group" aria-label="Insert a direction">
      {#each directions as d (d.tag)}
        <button
          type="button"
          class="tag"
          onclick={() => insert(d.tag)}
          title={d.exact ? 'Applied directly' : 'Approximated with speed, pitch and loudness'}
          >[{d.tag}]{d.exact ? '' : ' ≈'}</button
        >
      {/each}
    </div>
    <p class="hint">≈ means the built-in voices can only approximate it.</p>
  {/if}

  <div class="cast">
    {#if speakers.length}
      {#each speakers as name (name)}
        <label
          >{name}
          <select
            value={cast[name.toLowerCase()]}
            onchange={(e) => (chosen = { ...chosen, [name.toLowerCase()]: e.currentTarget.value })}
            aria-label={`Voice for ${name}`}
          >
            {#each voices as v (v.id)}<option value={v.id}>{v.name} · {v.language}</option>{/each}
          </select></label
        >
      {/each}
    {/if}
    <label
      >{speakers.length ? 'Narration (lines without a name)' : 'Voice'}
      <select bind:value={voice}>
        {#each voices as v (v.id)}<option value={v.id}>{v.name} · {v.language}</option>{/each}
      </select></label
    >
  </div>

  <div class="row">
    <button class="btn" type="submit" disabled={busy || running}>Perform</button>
    {#if running}<button class="btn secondary" type="button" onclick={cancel}>Stop</button>{/if}
    {#if job && !running && ready}
      <a
        class="btn secondary"
        href={`/api/shark/jobs/${job.job}/performance.wav`}
        download="shark-audio-performance.wav">Download performance</a
      >
    {/if}
  </div>
  <p class="status" role="status" aria-live="polite">{status}</p>
</form>

<audio bind:this={player} onended={() => (playing = null)}></audio>

{#if job}
  <section aria-labelledby="perf-h">
    <h2 id="perf-h">Performance <span class="hint">{ready} of {job.chunks.length} ready</span></h2>
    {#each job.chunks as chunk (chunk.index)}
      <article class="card chunk" data-state={chunk.state}>
        <header>
          <strong>{chunk.speaker || 'Narration'}</strong>
          <span class="hint"
            >{chunk.state === 'rendering' ? 'Recording…' : chunk.state === 'waiting' ? 'Waiting' : ''}</span
          >
        </header>
        <p class="text">{chunk.text}</p>
        {#if chunk.readout.length}
          <ul class="readout">
            {#each chunk.readout as r, i (i)}
              <li class={r.status}><strong>[{r.tag}]</strong> {STATUS_LABEL[r.status]}: {r.how}</li>
            {/each}
          </ul>
        {/if}
        {#if chunk.state === 'error'}<p class="error">{chunk.error}</p>{/if}
        {#if chunk.versions.length}
          <div class="row" role="group" aria-label="Versions">
            {#each chunk.versions as v (v.version)}
              <button
                type="button"
                class="btn secondary small"
                aria-pressed={chunk.selected === v.version}
                onclick={() => {
                  void select(chunk, v.version);
                  play(audioUrl(chunk, v.version));
                }}>▶ {v.version === 0 ? 'Take 1' : v.note} · {v.seconds}s</button
              >
            {/each}
          </div>
          {#if !running}
            <form
              class="revise row"
              onsubmit={(e) => {
                e.preventDefault();
                void revise(chunk, false);
              }}
            >
              <label class="grow"
                ><span class="sr">Note for this chunk</span>
                <input
                  type="text"
                  maxlength="200"
                  placeholder="gentler, a bit sadder"
                  bind:value={notes[chunk.index]}
                /></label
              >
              <button class="btn secondary" type="submit">Revise</button>
              <button class="btn secondary" type="button" onclick={() => revise(chunk, true)}>Retake</button>
            </form>
          {/if}
          {#if feedback[chunk.index]}<p class="status" aria-live="polite">{feedback[chunk.index]}</p>{/if}
        {/if}
      </article>
    {/each}
  </section>
{/if}

<p class="hint credit">
  Directing ideas inspired by Fish Audio's published work; {PRODUCT} uses its own code with the local Kokoro and Chatterbox
  voices.
</p>

<style>
  textarea {
    width: 100%;
    font: inherit;
  }
  .tags {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin: 10px 0 4px;
  }
  .tag {
    font: inherit;
    font-size: 0.85rem;
    padding: 4px 9px;
    border: 1px solid var(--line);
    border-radius: 999px;
    background: var(--bg);
    color: var(--ink);
    cursor: pointer;
  }
  .cast {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 10px;
    margin: 14px 0;
  }
  .cast label {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
  }
  .chunk header {
    display: flex;
    justify-content: space-between;
  }
  .chunk[data-state='waiting'] {
    opacity: 0.6;
  }
  .text {
    margin: 6px 0;
  }
  .readout {
    margin: 0 0 10px;
    padding-left: 18px;
    font-size: 0.9rem;
  }
  .readout .approximated {
    color: var(--warn);
  }
  .readout .unavailable,
  .readout .unknown {
    color: var(--muted);
  }
  .small {
    padding: 6px 10px;
    font-size: 0.85rem;
  }
  [aria-pressed='true'] {
    border-color: var(--accent);
    box-shadow: inset 0 -2px 0 var(--accent);
  }
  .revise {
    margin-top: 10px;
  }
  .grow {
    flex: 1 1 220px;
  }
  .grow input {
    width: 100%;
  }
  .sr {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
  }
  .credit {
    margin-top: 24px;
  }
</style>
