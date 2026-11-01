<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { PRODUCT } from '#lib/nav.ts';
  import {
    api,
    collectionSummary,
    keep,
    MAX_SECONDS,
    MIN_SECONDS,
    POLL_MS,
    post,
    sampleInfo,
    sampleLabel,
    sourceSummary,
    turnLabel,
    type Library,
    type Person,
    type PersonDetail,
    type PreviewJob,
    type PreviewResult,
    type Source,
    type SourceSummary,
    type Turn,
    type Version,
  } from '#lib/samples/samples.ts';

  let status = $state('Loading the local library...');
  let statusError = $state(false);
  let busy = $state<Record<string, boolean>>({});
  let installed = $state(true);
  let settled = $state(false);

  let people = $state<Person[]>([]);
  let sources = $state<SourceSummary[]>([]);
  let personEmpty = $state('Create a person below');
  let sourceEmpty = $state('No recordings yet');
  let personKey = $state('');
  let sourceKey = $state('');

  let importForm: HTMLFormElement | undefined = $state();
  let mediaFiles = $state<FileList | null>(null);
  let newName = $state('');
  let newConsent = $state(false);

  let sourceStatus = $state('');
  let sourceError = $state(false);
  let running = $state(false);
  let retryable = $state(false);
  let reviewing = $state(false);
  let turns = $state<Turn[]>([]);
  let originalSrc = $state('');
  let dialogueSrc = $state('');
  let sampleStart = $state<number | null>(0);
  let sampleEnd = $state<number | null>(5);
  let useCleaned = $state(true);
  let sampleConsent = $state(false);
  let selectionShown = $state(false);
  let originalAudio: HTMLAudioElement | undefined = $state();
  let dialogueAudio: HTMLAudioElement | undefined = $state();
  let selectionAudio: HTMLAudioElement | undefined = $state();
  let sampleStartInput: HTMLInputElement | undefined = $state();

  let detail = $state<PersonDetail | null>(null);
  let checked = $state<Record<string, boolean>>({});
  let previewText = $state('Hello. This is a reference comparison using the same sentence.');
  let previews = $state<Record<string, string>>({});

  let sourceGeneration = 0;
  let personGeneration = 0;
  let destroyed = false;
  const timers = new Set<ReturnType<typeof setTimeout>>();

  const who = $derived(people.find((person) => person.id === personKey));
  const selected = $derived(detail ? detail.samples.filter((sample) => checked[sample.id]) : []);
  const total = $derived(selected.reduce((sum, sample) => sum + sample.seconds, 0));
  const collectionName = $derived(
    !who
      ? 'Choose a person to see their samples.'
      : detail
        ? collectionSummary(detail)
        : `${who.name}: loading samples...`,
  );

  function wait(ms: number): Promise<void> {
    return new Promise((resolve) => {
      const timer = setTimeout(() => {
        timers.delete(timer);
        resolve();
      }, ms);
      timers.add(timer);
    });
  }

  onMount(() => void run(null, refresh));

  onDestroy(() => {
    destroyed = true;
    sourceGeneration++;
    personGeneration++;
    for (const timer of timers) clearTimeout(timer);
    timers.clear();
  });

  function showStatus(message: string, error = false) {
    status = message;
    statusError = error;
  }

  async function run(key: string | null, action: () => Promise<void>) {
    if (key) busy[key] = true;
    try {
      await action();
    } catch (error) {
      showStatus(
        error instanceof Error ? error.message : 'The operation failed. Retry when the local server is available.',
        true,
      );
    } finally {
      if (key) busy[key] = false;
      settled = true;
    }
  }

  function setSources(rows: SourceSummary[]) {
    sources = rows;
    sourceEmpty = 'Choose an imported recording';
    sourceKey = keep(sourceKey, rows);
  }

  async function refresh() {
    const data = await api<Library>('/api/samples');
    people = data.people;
    personEmpty = 'Choose a person';
    personKey = keep(personKey, people);
    setSources(data.sources);
    installed = data.installed;
    showStatus(
      data.installed ? 'Local media engine ready. No audio is uploaded to a cloud service.' : data.setup,
      !data.installed,
    );
    await loadPerson();
    await loadSource();
  }

  function stopSelection() {
    if (!selectionAudio) return;
    selectionAudio.pause();
    selectionAudio.ontimeupdate = null;
  }

  async function loadSource() {
    const generation = ++sourceGeneration;
    const key = sourceKey;
    reviewing = false;
    retryable = false;
    running = false;
    originalAudio?.pause();
    dialogueAudio?.pause();
    stopSelection();
    selectionShown = false;
    if (!key) {
      sourceStatus = 'Import a recording to review its speakers.';
      return;
    }
    for (;;) {
      const source = await api<Source>(`/api/samples/sources/${key}`);
      if (generation !== sourceGeneration) return;
      sourceStatus = source.error || source.step;
      sourceError = source.status === 'error';
      retryable = source.status === 'error';
      running = source.status === 'running';
      if (source.status === 'done') {
        reviewing = true;
        originalSrc = `/api/samples/sources/${key}/audio/original`;
        dialogueSrc = `/api/samples/sources/${key}/audio/dialogue`;
        sourceStatus = sourceSummary(source);
        turns = source.segments ?? [];
        sampleStart = 0;
        sampleEnd = Math.min(5, source.duration ?? 5);
        sampleConsent = false;
        return;
      }
      if (source.status === 'error') return;
      await wait(POLL_MS);
      if (destroyed || generation !== sourceGeneration) return;
    }
  }

  async function loadPerson() {
    const generation = ++personGeneration;
    const key = personKey;
    detail = null;
    checked = {};
    previews = {};
    sampleConsent = false;
    if (!key) return;
    const data = await api<PersonDetail>(`/api/samples/people/${key}`);
    if (generation !== personGeneration) return;
    detail = data;
  }

  function importMedia(event: SubmitEvent) {
    event.preventDefault();
    void run('import', async () => {
      if (!importForm) return;
      const form = new FormData(importForm);
      if (!mediaFiles?.length) form.delete('file');
      showStatus('Uploading to the local app. Keep this page open until the upload finishes.');
      const result = await api<{ id: string }>('/api/samples/sources', { method: 'POST', body: form });
      const data = await api<Library>('/api/samples');
      setSources(data.sources);
      sourceKey = result.id;
      showStatus('Import accepted. Analyzing locally; you can revisit the saved source after a refresh.');
      await loadSource();
    });
  }

  function createPerson(event: SubmitEvent) {
    event.preventDefault();
    void run('person', async () => {
      const person = await post<Person>('/api/samples/people', { name: newName, consent: newConsent });
      people = [person, ...people];
      personEmpty = 'Choose a person';
      personKey = person.id;
      newName = '';
      newConsent = false;
      await loadPerson();
      showStatus(`Created collection: ${person.name}.`);
    });
  }

  function retry() {
    void run('retry', async () => {
      await post(`/api/samples/sources/${sourceKey}/retry`, {});
      await loadSource();
    });
  }

  function pickTurn(turn: Turn) {
    sampleStart = turn.start;
    sampleEnd = turn.end;
    sampleConsent = false;
    sampleStartInput?.focus();
  }

  function listen() {
    void run('listen', async () => {
      const audio = selectionAudio;
      if (!audio) return;
      stopSelection();
      originalAudio?.pause();
      dialogueAudio?.pause();
      // Set the element directly so currentTime and play() apply to the new source immediately.
      audio.src = useCleaned ? dialogueSrc : originalSrc;
      selectionShown = true;
      const start = sampleStart ?? NaN;
      const end = sampleEnd ?? NaN;
      if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end <= start)
        throw new Error('Choose a valid selection start and end.');
      audio.currentTime = start;
      await audio.play();
      audio.onpause = () => {
        audio.ontimeupdate = null;
      };
      audio.ontimeupdate = () => {
        if (audio.currentTime >= end) {
          audio.ontimeupdate = null;
          audio.pause();
        }
      };
    });
  }

  function saveSample(event: SubmitEvent) {
    event.preventDefault();
    void run('save', async () => {
      await post(`/api/samples/people/${personKey}/samples`, {
        source: sourceKey,
        start: Number(sampleStart),
        end: Number(sampleEnd),
        cleaned: useCleaned,
        consent: sampleConsent,
      });
      await loadPerson();
      showStatus('Approved sample saved. The original recording and previous reference versions are unchanged.');
    });
  }

  function buildVersion() {
    void run('build', async () => {
      const version = await post<Version>(`/api/samples/people/${personKey}/versions`, {
        samples: selected.map((sample) => sample.id),
      });
      await loadPerson();
      showStatus(
        `Created ${version.name}. Compare it before marking it preferred. This is a new reference, not model training.`,
      );
    });
  }

  function preview(version: Version) {
    void run(`preview:${version.id}`, async () => {
      const form = new FormData();
      form.set('voice', version.id);
      form.set('text', previewText);
      const job = await api<PreviewJob>('/api/clone/preview', { method: 'POST', body: form });
      showStatus(`Rendering ${version.name}. Local CPU rendering can take several minutes.`);
      for (let attempt = 0; attempt < 600; attempt++) {
        await wait(POLL_MS);
        if (destroyed) return;
        const result = await api<PreviewResult>(`/api/clone/preview/${job.job}`);
        if (result.status === 'error') throw new Error(result.error);
        if (result.status === 'done') {
          previews[version.id] = `/api/clone/preview/${job.job}/audio`;
          showStatus(`Comparison ready: ${version.name}. Press play to listen.`);
          return;
        }
      }
      throw new Error('Preview is taking longer than expected. Check the local server before retrying.');
    });
  }

  function prefer(version: Version) {
    const key = personKey;
    void run(`prefer:${version.id}`, async () => {
      await post(`/api/samples/people/${key}/active`, { voice: version.id });
      await loadPerson();
      showStatus(`${version.name} is preferred. Existing Studio scripts are unchanged.`);
    });
  }

  function resetConsent() {
    sampleConsent = false;
  }
</script>

<svelte:head><title>Voice sample collections · {PRODUCT}</title></svelte:head>

<h1>Voice sample collections</h1>
<p class="lede">
  Keep each person's approved recordings together. Add more clips later and compare new reference versions without
  replacing old ones.
</p>
<p class="note">
  Local reference-based cloning, not model training. Speaker labels are suggestions: review every selection. Background
  separation cannot reliably isolate people speaking at the same time.
</p>
<p id="status" class="status" class:error={statusError} role="status" aria-live="polite">{status}</p>
<button id="refresh" class="btn secondary" type="button" disabled={busy.refresh} onclick={() => run('refresh', refresh)}
  >Refresh library</button
>
<div class="grid" style="margin-top:16px">
  <section class="card" aria-labelledby="importHeading">
    <h2 id="importHeading">1. Import a recording</h2>
    <form id="importForm" bind:this={importForm} onsubmit={importMedia}>
      <label class="field"
        >Audio or video file<input
          id="mediaFile"
          name="file"
          type="file"
          accept=".wav,.mp3,.mp4,.m4a,.flac,.webm,.ogg,.mov,.mkv,.opus"
          bind:files={mediaFiles}
        /></label
      >
      <label class="field"
        >Or a public YouTube video URL<input
          id="mediaUrl"
          name="url"
          type="url"
          placeholder="https://www.youtube.com/watch?v=..."
        /></label
      >
      <p class="hint">
        Files up to 250 MB. Analyze a 5 to 120 second window. For larger movies, export a clip first. YouTube imports
        download audio from videos up to 30 minutes and may be unavailable.
      </p>
      <div class="row">
        <label class="field"
          >Start in source (seconds)<input
            name="start"
            type="number"
            min="0"
            max="28800"
            step="0.1"
            value="0"
            required
          /></label
        >
        <label class="field"
          >Window length (seconds)<input
            name="seconds"
            type="number"
            min="5"
            max="120"
            step="0.1"
            value="30"
            required
          /></label
        >
      </div>
      <label class="field"
        >Expected speakers (0 = detect automatically)<input
          name="speakers"
          type="number"
          min="0"
          max="16"
          value="0"
          required
        /></label
      >
      <label class="check"
        ><input name="separate" type="checkbox" value="true" />Separate vocals from background music (slower; may
        introduce artifacts)</label
      >
      <label class="check"
        ><input name="consent" type="checkbox" value="true" required />I have permission to process this recording and
        clone its selected voices.</label
      >
      <button id="importButton" class="btn" type="submit" disabled={busy.import || !installed}
        >Import and detect speakers</button
      >
    </form>
  </section>
  <section class="card" aria-labelledby="peopleHeading">
    <h2 id="peopleHeading">2. Choose a person</h2>
    <label class="field"
      >Saved person<select id="personSelect" bind:value={personKey} onchange={() => run(null, loadPerson)}>
        <option value="">{personEmpty}</option>
        {#each people as person (person.id)}<option value={person.id}>{person.name}</option>{/each}
      </select></label
    >
    <form id="personForm" onsubmit={createPerson}>
      <label class="field"
        >New person's name<input
          id="personName"
          name="name"
          type="text"
          maxlength="60"
          required
          bind:value={newName}
        /></label
      >
      <label class="check"
        ><input name="consent" type="checkbox" required bind:checked={newConsent} />I own this voice or have permission
        to clone it.</label
      >
      <button class="btn secondary" type="submit" disabled={busy.person}>Create collection</button>
    </form>
    <p class="hint">
      Choose the same person when adding samples from another recording. Speaker numbers only apply to the current
      source.
    </p>
  </section>
</div>
<section class="card" aria-labelledby="reviewHeading">
  <h2 id="reviewHeading">3. Listen and save solo speech</h2>
  <label class="field"
    >Imported recording<select id="sourceSelect" bind:value={sourceKey} onchange={() => run(null, loadSource)}>
      <option value="">{sourceEmpty}</option>
      {#each sources as source (source.id)}<option value={source.id}>{source.name}</option>{/each}
    </select></label
  >
  <p id="sourceStatus" class="status" class:error={sourceError} role="status">{sourceStatus}</p>
  <div id="importProgress" hidden={!running}>
    <progress aria-label="Analyzing recording"></progress>
    <span class="static-status hint">Analyzing recording...</span>
  </div>
  <button id="retry" type="button" class="btn secondary" hidden={!retryable} disabled={busy.retry} onclick={retry}
    >Retry saved source</button
  >
  <div id="review" hidden={!reviewing}>
    <p class="hint">
      Times below are relative to the imported window. Pick a detected turn or enter a range manually. Listen before
      assigning it to a person.
    </p>
    <div id="turns" class="turns" role="group" aria-label="Detected speaker turns">
      {#each turns as turn, index (index)}
        <button type="button" class="btn secondary" onclick={() => pickTurn(turn)}>{turnLabel(turn)}</button>
      {:else}
        No speech turns detected. You can listen and select a range manually.
      {/each}
    </div>
    <div class="grid">
      <div>
        <h3>Original window</h3>
        <audio
          id="originalAudio"
          bind:this={originalAudio}
          src={originalSrc || undefined}
          controls
          preload="none"
          aria-label="Original audio window"
        ></audio>
      </div>
      <div>
        <h3>Dialogue window</h3>
        <audio
          id="dialogueAudio"
          bind:this={dialogueAudio}
          src={dialogueSrc || undefined}
          controls
          preload="none"
          aria-label="Dialogue audio window"
        ></audio>
      </div>
    </div>
    <form id="sampleForm" onsubmit={saveSample}>
      <div class="row">
        <label class="field"
          >Selection start (seconds)<input
            id="sampleStart"
            type="number"
            min="0"
            max="120"
            step="0.001"
            required
            bind:this={sampleStartInput}
            bind:value={sampleStart}
            onchange={resetConsent}
          /></label
        >
        <label class="field"
          >Selection end (seconds)<input
            id="sampleEnd"
            type="number"
            min="0.5"
            max="121"
            step="0.001"
            required
            bind:value={sampleEnd}
            onchange={resetConsent}
          /></label
        >
        <button id="listen" type="button" class="btn secondary" disabled={busy.listen} onclick={listen}
          >Listen to selection</button
        >
      </div>
      <audio
        id="selectionAudio"
        bind:this={selectionAudio}
        controls
        preload="none"
        aria-label="Selected audio range"
        hidden={!selectionShown}
      ></audio>
      <label class="check"
        ><input id="useCleaned" type="checkbox" bind:checked={useCleaned} onchange={resetConsent} />Use the dialogue
        version (uncheck to keep original audio)</label
      >
      <label class="check"
        ><input id="sampleConsent" type="checkbox" required bind:checked={sampleConsent} />I listened: this selection
        contains only the permitted person's voice.</label
      >
      <p id="destination" class="hint">{who ? `Save to: ${who.name}` : 'Choose a person before saving.'}</p>
      <button id="saveSample" type="submit" class="btn" disabled={!personKey || busy.save}>Save approved sample</button>
    </form>
  </div>
</section>
<section class="card" aria-labelledby="collectionHeading">
  <h2 id="collectionHeading">4. Build and compare reference versions</h2>
  <p id="collectionName" class="hint">{collectionName}</p>
  <ul id="samples" class="items">
    {#each detail?.samples ?? [] as sample (sample.id)}
      <li>
        <label class="check"
          ><input type="checkbox" value={sample.id} bind:checked={checked[sample.id]} />{sampleLabel(sample)}</label
        >
        <p class="hint">{sampleInfo(sample)}</p>
        <audio
          controls
          preload="none"
          src={`/api/samples/audio/${sample.id}`}
          aria-label={`Saved sample from ${sample.source_name}`}
        ></audio>
      </li>
    {/each}
  </ul>
  <p id="selectionTotal" class="status">
    {!settled
      ? 'Select samples totaling 5 to 20 seconds.'
      : `${total.toFixed(2)} seconds selected. Choose 5 to 20 seconds total.`}
  </p>
  <button
    id="buildVersion"
    type="button"
    class="btn"
    disabled={!personKey || total < MIN_SECONDS || total > MAX_SECONDS || busy.build}
    onclick={buildVersion}>Build reference version</button
  >
  <p class="hint">
    Only checked samples enter the new reference. Adding recordings does not train a model or guarantee better results.
    Previous versions remain available in Voice Lab and Studio.
  </p>
  <label class="field"
    >Comparison sentence<textarea id="previewText" rows="2" maxlength="500" bind:value={previewText}></textarea></label
  >
  <ul id="versions" class="items">
    {#each detail?.versions ?? [] as version (version.id)}
      <li>
        <strong>{version.name}{detail?.active === version.id ? ' (preferred)' : ''}</strong>
        <div class="row">
          <button
            type="button"
            class="btn secondary"
            disabled={busy[`preview:${version.id}`]}
            onclick={() => preview(version)}>Preview comparison</button
          >
          {#if detail?.active !== version.id}
            <button
              type="button"
              class="btn secondary"
              disabled={busy[`prefer:${version.id}`]}
              onclick={() => prefer(version)}>Mark preferred</button
            >
          {/if}
        </div>
        <audio
          controls
          preload="none"
          src={previews[version.id]}
          aria-label={`Comparison for ${version.name}`}
          hidden={!previews[version.id]}
        ></audio>
      </li>
    {:else}
      {#if detail}No reference versions yet.{/if}
    {/each}
  </ul>
</section>
<p class="hint">
  Recordings stay in this app's local data folder. Keep a backup of the whole folder. The sample library has a 2 GB
  budget and requires 1 GB free disk space.
</p>

<style>
  .grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 16px;
    align-items: start;
  }
  .grid > * {
    min-width: 0;
  }
  .field {
    display: flex;
    flex-direction: column;
    gap: 4px;
    margin-bottom: 12px;
  }
  .row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 12px;
    margin: 12px 0;
  }
  .row > * {
    min-width: 0;
  }
  .check {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    font-weight: 400;
    margin: 12px 0;
  }
  .check input {
    margin-top: 6px;
    flex-shrink: 0;
  }
  input[type='file'] {
    width: 100%;
    min-width: 0;
    max-width: 100%;
    font: inherit;
  }
  input[type='url'] {
    font: inherit;
    padding: 9px 11px;
    border: 1px solid var(--muted);
    border-radius: 8px;
    background: var(--bg);
    color: var(--ink);
    width: 100%;
  }
  input[type='number'],
  input[type='text'],
  select,
  textarea,
  .btn.secondary {
    border-color: var(--muted);
  }
  select {
    padding-inline-end: 28px;
  }
  audio {
    width: 100%;
    max-width: 500px;
    display: block;
    margin: 8px 0;
  }
  audio[hidden] {
    display: none;
  }
  .items {
    list-style: none;
    padding: 0;
    margin: 0;
  }
  .items > li {
    padding: 12px 0;
    border-top: 1px solid var(--line);
    overflow-wrap: anywhere;
  }
  .turns {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    max-height: 240px;
    overflow: auto;
    padding: 4px;
  }
  .turns button {
    font-variant-numeric: tabular-nums;
  }
  h2 {
    margin-top: 0;
    font-size: 1.15rem;
  }
  h3 {
    font-size: 1rem;
  }
  .note {
    border-left: 3px solid var(--warn);
    padding-left: 12px;
  }
  p {
    max-width: 78ch;
  }
  progress {
    width: 100%;
    accent-color: var(--accent);
  }
  #importProgress .static-status {
    display: none;
  }
  @media (prefers-reduced-motion: reduce) {
    #importProgress progress {
      display: none;
    }
    #importProgress .static-status {
      display: inline;
    }
  }
  @media (max-width: 700px) {
    .grid {
      grid-template-columns: minmax(0, 1fr);
    }
    .card {
      padding: 16px;
    }
  }
</style>
