<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { request } from '#lib/api.ts';
  import { PRODUCT } from '#lib/nav.ts';
  import {
    acceptFiles,
    actions,
    batchSummary,
    clock,
    metricRows,
    queueLine,
    resultSettings,
    resultTitle,
    runJob,
    scopeNote,
    section,
    suggestionText,
    responseJSON,
    type Bounds,
    type JobResult,
    type Mode,
    type QueueItem,
    type Snapshot,
  } from '#lib/clean/queue.ts';
  import {
    DEFAULT_TEMPLATE,
    MAX_SAVED,
    parseSaved,
    percent,
    SAVED_KEY,
    settingsFor,
    SLIDERS,
    templateFor,
    templateLabel,
    TEMPLATES,
    validatePresets,
    type Controls,
    type Presets,
    type SavedTemplates,
    type SliderKey,
  } from '#lib/clean/templates.ts';
  import { defaultVoice, voiceGroups, type CatalogVoice, type VoiceGroup } from '#lib/clean/voices.ts';

  type Shown = { job: string; result: JobResult; name: string; label: string; id: number };

  let tab = $state<'clean' | 'speak'>('clean');

  // Templates and controls.
  let presets: Presets | null = null;
  let templatesReady = $state(false);
  let saved = $state<SavedTemplates>({});
  let templateKey = $state(DEFAULT_TEMPLATE);
  let controls = $state<Controls | null>(null);
  let templateHelp = $state('Loading settings…');
  let templateState = $state('');
  let templateName = $state('');
  let savedStatus = $state('');

  // Queue and processing.
  let queue = $state<QueueItem[]>([]);
  let activeIndex = $state(-1);
  let busy = $state(false);
  let batching = $state(false);
  let stopRequested = $state(false);
  let downloading = $state(false);
  let over = $state(false);
  let previewStart = $state(0);
  let previewLength = $state('15');
  let suggestion = $state('');
  let suggestionKey = $state<string | null>(null);
  let status = $state('');
  let statusError = $state(false);
  let queueStatus = $state('');
  let progVisible = $state(false);
  let progress = $state(0);
  let input: HTMLInputElement | undefined = $state();

  // Comparison.
  let shown = $state<Shown | null>(null);
  let shownCount = 0;
  let before: HTMLAudioElement | undefined = $state();
  let after: HTMLAudioElement | undefined = $state();
  let activeTrack = $state(0);
  let playLabel = $state('Play');
  let abStatus = $state('');
  let seekMax = $state(0);
  let seekValue = $state(0);
  let abTime = $state('0:00');
  let playbackVersion = 0;

  // Text to voice.
  let text = $state(
    'Hi there! Thanks for stopping by. Today I want to show you something that will save you hours every week.',
  );
  let groups = $state<VoiceGroup[] | null>(null);
  let voice = $state('af_heart');
  let speed = $state(1);
  let engine = $state('kokoro');
  let speaking = $state(false);
  let speakStatus = $state('');
  let speakError = $state(false);
  let speakUrl = $state<string | null>(null);
  let speakAudio: HTMLAudioElement | undefined = $state();

  const file = $derived(queue[activeIndex]?.file ?? null);
  const savedSelected = $derived(Object.hasOwn(saved, templateKey));
  const disabled = $derived(actions({ templatesReady, hasFile: !!file, busy, queue, savedSelected, downloading }));
  const rows = $derived(shown ? metricRows(shown.result.before, shown.result.after) : []);

  onMount(() => {
    try {
      saved = parseSaved(localStorage.getItem(SAVED_KEY));
    } catch {
      // Corrupt or blocked storage must not disable uploads.
    }
    void loadPresets();
    void loadVoices();
    if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});
  });

  onDestroy(() => {
    if (speakUrl) URL.revokeObjectURL(speakUrl);
  });

  async function loadPresets() {
    try {
      const response = await fetch('/api/presets');
      if (!response.ok) throw new Error('Settings unavailable');
      presets = validatePresets(await response.json());
      templatesReady = true;
      applyTemplate();
    } catch {
      templateHelp = 'Could not load templates. Refresh the page to try again.';
    }
  }

  async function loadVoices() {
    try {
      const response = await fetch('/api/voices');
      if (!response.ok) return;
      const body: unknown = await response.json();
      if (!body || typeof body !== 'object' || !('catalog' in body) || !Array.isArray(body.catalog)) return;
      const catalog = body.catalog as CatalogVoice[];
      groups = voiceGroups(catalog);
      voice = defaultVoice(catalog);
    } catch {
      // The single default voice stays available.
    }
  }

  function applyTemplate() {
    const template = templateFor(templateKey, saved);
    if (!templatesReady || !presets || !template) return;
    controls = settingsFor(template, presets);
    templateHelp = template.description;
    templateState = 'Template applied. All controls updated; you can fine-tune them below.';
  }

  function setControl(key: SliderKey, value: number) {
    if (controls) controls[key] = value;
    templateState = 'Custom settings based on this template. Reset restores its values.';
  }

  function writeSaved(next: SavedTemplates): boolean {
    try {
      localStorage.setItem(SAVED_KEY, JSON.stringify(next));
      return true;
    } catch {
      return false;
    }
  }

  function saveTemplate() {
    const name = templateName.trim();
    if (!name) return void (savedStatus = 'Enter a name first.');
    if (Object.keys(saved).length >= MAX_SAVED)
      return void (savedStatus = 'Limit of 30 saved templates. Delete one first.');
    const template = templateFor(templateKey, saved);
    if (!template || !controls) return;
    const key = 'saved-' + crypto.randomUUID();
    const next = { ...saved, [key]: { name, preset: template.preset, settings: { ...controls } } };
    if (!writeSaved(next))
      return void (savedStatus = 'Browser storage is unavailable or full. Your settings were not saved.');
    saved = next;
    templateKey = key;
    applyTemplate();
    savedStatus = 'Saved in this browser.';
  }

  function deleteTemplate() {
    if (!savedSelected) return;
    const next = { ...saved };
    delete next[templateKey];
    if (!writeSaved(next)) return void (savedStatus = 'Could not update browser storage. Nothing deleted.');
    saved = next;
    templateKey = DEFAULT_TEMPLATE;
    applyTemplate();
    savedStatus = 'Saved template deleted.';
  }

  function setStatus(message: string, error = false) {
    status = message;
    statusError = error;
  }

  function selectFile(index: number) {
    activeIndex = index;
    suggestionKey = null;
    suggestion = '';
  }

  function pickMany(files: FileList | null | undefined) {
    if (busy) return setStatus('Wait for the current operation before adding files.', true);
    const { accepted, rejected } = acceptFiles(queue.length, Array.from(files ?? []));
    if (accepted.length) {
      const index = queue.length;
      queue.push(...accepted);
      selectFile(index);
    }
    setStatus(rejected.join(' '), rejected.length > 0);
  }

  function chooseFile() {
    if (!busy) input?.click();
  }

  function dropKey(event: KeyboardEvent) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      chooseFile();
    }
  }

  function dropFiles(event: DragEvent) {
    event.preventDefault();
    over = false;
    pickMany(event.dataTransfer?.files);
  }

  function fileChosen() {
    if (!input) return;
    pickMany(input.files);
    input.value = '';
  }

  function clearQueue() {
    if (busy) return;
    queue = [];
    selectFile(-1);
    pauseTracks();
    shown = null;
    queueStatus = 'Queue cleared. Previously downloaded files are unchanged.';
  }

  function snapshot(): Snapshot | null {
    const template = templateFor(templateKey, saved);
    if (!template || !controls) return null;
    const custom = templateState.startsWith('Custom') ? ' (custom)' : '';
    return { preset: template.preset, controls: { ...controls }, label: templateLabel(templateKey, saved) + custom };
  }

  function job(item: QueueItem, mode: Mode, settings: Snapshot, bounds: Bounds) {
    progVisible = true;
    return runJob(item, mode, settings, bounds, {
      fetch: (url, init) => fetch(url, init),
      status: (message) => setStatus(message),
      progress: (fraction) => (progress = Math.round(fraction * 100)),
    });
  }

  function errorText(error: unknown): string {
    return error instanceof Error ? error.message : String(error);
  }

  async function runSelected(mode: Mode) {
    const item = queue[activeIndex];
    const settings = snapshot();
    if (busy || !file || !templatesReady || !item || !settings) return;
    let bounds: Bounds;
    try {
      bounds = mode === 'clean' ? { start: 0, seconds: 15 } : section(previewStart, Number(previewLength));
    } catch (error) {
      return setStatus(errorText(error), true);
    }
    busy = true;
    pauseTracks();
    if (mode === 'clean') Object.assign(item, { status: 'processing', error: null, job: null, result: null });
    try {
      const done = await job(item, mode, settings, bounds);
      if (mode === 'analyze') {
        const key = done.result.suggestion?.template ?? '';
        suggestionKey = key;
        const known = TEMPLATES.some((t) => t.key === key) || Object.hasOwn(saved, key);
        suggestion = suggestionText(done.result, known ? templateLabel(key, saved) : key);
      } else {
        showResult(done.job, done.result, item.file.name, settings.label);
        if (mode === 'clean') Object.assign(item, { ...done, status: 'done', label: settings.label });
      }
      setStatus(
        mode === 'preview'
          ? 'Preview ready. Change a template and preview the same section again to compare.'
          : 'Done.',
      );
    } catch (error) {
      if (mode === 'clean') Object.assign(item, { status: 'error', error: errorText(error) });
      setStatus(errorText(error), true);
    } finally {
      busy = false;
      progVisible = false;
    }
  }

  function applySuggestion() {
    if (!suggestionKey || busy) return;
    templateKey = suggestionKey;
    applyTemplate();
  }

  async function processQueue() {
    const settings = snapshot();
    if (busy || !templatesReady || !settings) return;
    stopRequested = false;
    busy = true;
    batching = true;
    pauseTracks();
    let completed = 0,
      failed = 0;
    try {
      for (const item of queue.filter((q) => q.status !== 'done')) {
        if (stopRequested) break;
        Object.assign(item, { status: 'processing', error: null, job: null, result: null });
        try {
          const done = await job(item, 'clean', settings, { start: 0, seconds: 15 });
          Object.assign(item, { ...done, status: 'done', label: settings.label });
          completed++;
          showResult(done.job, done.result, item.file.name, settings.label);
        } catch (error) {
          Object.assign(item, { status: 'error', error: errorText(error) });
          failed++;
        }
      }
      queueStatus = batchSummary(completed, failed, stopRequested);
      setStatus('Batch finished. Results remain in the queue.');
    } finally {
      busy = false;
      batching = false;
      progVisible = false;
    }
  }

  function stopQueue() {
    stopRequested = true;
    queueStatus = 'Will stop after the current file finishes.';
  }

  async function downloadBatch() {
    downloading = true;
    try {
      const response = await fetch('/api/batch-download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ jobs: queue.flatMap((q) => (q.job ? [q.job] : [])) }),
      });
      if (!response.ok) await responseJSON(response);
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = url;
      link.download = 'natural-voice-batch.zip';
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (error) {
      queueStatus = errorText(error);
    } finally {
      downloading = false;
    }
  }

  // A/B switches between preloaded, loudness-matched listening copies at the same time position.
  function tracks(): HTMLAudioElement[] {
    return before && after ? [before, after] : [];
  }

  function pauseTracks() {
    playbackVersion++;
    for (const t of tracks()) t.pause();
    playLabel = 'Play';
  }

  function updateTime() {
    const track = tracks()[activeTrack];
    if (!track) return;
    const duration = Number.isFinite(track.duration) ? track.duration : 0;
    seekMax = duration;
    seekValue = track.currentTime;
    abTime = `${clock(track.currentTime)} / ${clock(duration)}`;
  }

  function loaded(target: HTMLAudioElement) {
    return new Promise<void>((resolve, reject) => {
      const timer = setTimeout(() => finish(new Error('Audio took too long to load. Try again.')), 15000);
      const ok = () => finish();
      const failed = () => finish(new Error('Comparison audio could not load.'));
      function finish(error?: Error) {
        clearTimeout(timer);
        target.removeEventListener('loadedmetadata', ok);
        target.removeEventListener('error', failed);
        if (error) reject(error);
        else resolve();
      }
      target.addEventListener('loadedmetadata', ok, { once: true });
      target.addEventListener('error', failed, { once: true });
    });
  }

  async function chooseTrack(index: number) {
    const list = tracks();
    const previous = list[activeTrack],
      target = list[index];
    if (!previous || !target || index === activeTrack) return;
    const time = previous.currentTime,
      playing = !previous.paused;
    pauseTracks();
    const version = playbackVersion;
    activeTrack = index;
    try {
      if (target.readyState < 1) await loaded(target);
      if (version !== playbackVersion) return;
      target.currentTime = Math.min(time, Number.isFinite(target.duration) ? target.duration : time);
      if (playing) {
        await target.play();
        playLabel = 'Pause';
      }
      abStatus = index ? 'B: Cleaned' : 'A: Original';
      updateTime();
    } catch (error) {
      abStatus = errorText(error);
    }
  }

  async function togglePlay() {
    const track = tracks()[activeTrack];
    if (!track) return;
    try {
      if (track.paused) {
        await track.play();
        playLabel = 'Pause';
      } else pauseTracks();
    } catch {
      abStatus = 'Playback could not start. Try again after the audio loads.';
    }
  }

  function seek(position: number) {
    for (const t of tracks()) if (t.readyState >= 1) t.currentTime = Math.min(position, t.duration);
    updateTime();
  }

  function showResult(jobId: string, result: JobResult, name: string, label: string) {
    pauseTracks();
    activeTrack = 0;
    abStatus = 'A: Original';
    seekValue = 0;
    shown = { job: jobId, result, name, label, id: ++shownCount };
  }

  async function speak() {
    speakError = false;
    speakStatus = 'Creating voice… (the first one takes a little longer)';
    speaking = true;
    const fd = new FormData();
    fd.append('text', text);
    fd.append('voice', voice);
    fd.append('speed', String(speed));
    fd.append('engine', engine);
    try {
      const response = await request('/api/speak', { method: 'POST', body: fd });
      if (speakUrl) URL.revokeObjectURL(speakUrl);
      speakUrl = URL.createObjectURL(await response.blob());
      speakStatus = '';
      if (speakAudio) {
        speakAudio.src = speakUrl;
        speakAudio.play().catch(() => {});
      }
    } catch (error) {
      speakStatus = errorText(error);
      speakError = true;
    }
    speaking = false;
  }
</script>

<svelte:head><title>{PRODUCT}</title></svelte:head>
<svelte:window ondragover={(e) => e.preventDefault()} ondrop={(e) => e.preventDefault()} />

{#snippet track(id: string, which: string, jobId: string, index: number)}
  <div {id} hidden>
    {#if index === 0}
      <audio
        src="/api/jobs/{jobId}/{which}"
        preload="auto"
        bind:this={before}
        ontimeupdate={updateTime}
        onloadedmetadata={updateTime}
        onended={() => (playLabel = 'Play')}
        onerror={() => (abStatus = 'Comparison audio unavailable. Try processing again.')}
      ></audio>
    {:else}
      <audio
        src="/api/jobs/{jobId}/{which}"
        preload="auto"
        bind:this={after}
        ontimeupdate={updateTime}
        onloadedmetadata={updateTime}
        onended={() => (playLabel = 'Play')}
        onerror={() => (abStatus = 'Comparison audio unavailable. Try processing again.')}
      ></audio>
    {/if}
  </div>
{/snippet}

<div class="clean">
  <header>
    <h1>{PRODUCT}</h1>
    <p>Make AI voices sound human: no metallic tone, no hollow echo. Runs on your computer.</p>
  </header>

  <div class="tabs" role="tablist">
    <button
      role="tab"
      id="tab-clean"
      aria-controls="panel-clean"
      aria-selected={tab === 'clean'}
      onclick={() => (tab = 'clean')}>Fix a voice</button
    >
    <button
      role="tab"
      id="tab-speak"
      aria-controls="panel-speak"
      aria-selected={tab === 'speak'}
      onclick={() => (tab = 'speak')}>Text to voice</button
    >
  </div>

  <div id="panel-clean" role="tabpanel" aria-labelledby="tab-clean" hidden={tab !== 'clean'}>
    <div class="card">
      <div
        class="drop"
        class:over
        id="drop"
        tabindex="0"
        role="button"
        aria-label="Choose an audio or video file"
        onclick={chooseFile}
        onkeydown={dropKey}
        ondragover={(e) => {
          e.preventDefault();
          over = true;
        }}
        ondragleave={() => (over = false)}
        ondrop={dropFiles}
      >
        <strong>Drop an audio or video file here</strong>
        <span class="hint">or click to choose: MP3, WAV, M4A, MP4, MOV, WEBM…</span>
        <div id="fileName" class="status">{file?.name ?? ''}</div>
      </div>
      <input type="file" id="file" accept="audio/*,video/*" multiple hidden bind:this={input} onchange={fileChosen} />
      <div id="queueSection" hidden={queue.length === 0}>
        <h2>File queue</h2>
        <p class="hint">
          Up to 20 files, 500 MB each. Select a file for a preview or suggestion. Batch uses the current settings for
          every queued file.
        </p>
        <label for="activeFile">Selected file</label><select
          id="activeFile"
          disabled={disabled.queue}
          value={String(activeIndex)}
          onchange={(e) => selectFile(Number(e.currentTarget.value))}
        >
          {#each queue as item, i (item)}
            <option value={String(i)}>{item.file.name}</option>
          {/each}
        </select>
        <ol id="queueList">
          {#each queue as item (item)}
            <li>
              {queueLine(item)}
              {#if item.result && item.job}
                {@const done = { job: item.job, result: item.result }}
                <button
                  disabled={busy}
                  onclick={() => showResult(done.job, done.result, item.file.name, item.label ?? '')}>Compare</button
                ><a href="/api/jobs/{item.job}/result" download="">Download</a>
              {/if}
            </li>
          {/each}
        </ol>
        <button class="btn secondary" id="batchBtn" disabled={disabled.batch} onclick={processQueue}
          >Process queue</button
        >
        <button class="btn secondary" id="stopQueue" hidden={!batching} disabled={stopRequested} onclick={stopQueue}
          >Stop after current file</button
        >
        <button class="btn secondary" id="batchDownload" disabled={disabled.download} onclick={downloadBatch}
          >Download completed files (.zip)</button
        >
        <button class="btn secondary" id="clearQueue" disabled={disabled.queue} onclick={clearQueue}>Clear queue</button
        >
        <div id="queueStatus" class="status" aria-live="polite">{queueStatus}</div>
      </div>

      <div class="templates">
        <label for="template">Quick template</label>
        <select
          id="template"
          aria-describedby="templateHelp templateState"
          disabled={disabled.settings}
          bind:value={templateKey}
          onchange={applyTemplate}
        >
          {#each TEMPLATES as t (t.key)}
            <option value={t.key}>{t.label}</option>
          {/each}
          {#each Object.entries(saved) as [key, item] (key)}
            <option value={key} data-saved="true">Saved: {item.name}</option>
          {/each}
        </select>
        <p id="templateHelp" class="hint">{templateHelp}</p>
        <p class="hint">Templates are starting points, not diagnoses. Built-in templates leave added room tone off.</p>
        <div id="templateState" class="status" aria-live="polite">{templateState}</div>
        <button
          type="button"
          class="btn secondary"
          id="resetTemplate"
          disabled={disabled.settings}
          onclick={applyTemplate}>Reset to template</button
        >
        <details>
          <summary>My saved templates</summary>
          <label for="templateName">Template name</label><input
            type="text"
            id="templateName"
            maxlength="60"
            placeholder="My podcast voice"
            bind:value={templateName}
          />
          <button
            type="button"
            class="btn secondary"
            id="saveTemplate"
            disabled={disabled.settings}
            onclick={saveTemplate}>Save current controls</button
          >
          <button
            type="button"
            class="btn secondary"
            id="deleteTemplate"
            disabled={disabled.remove}
            onclick={deleteTemplate}>Delete selected saved template</button
          >
          <p class="hint">Stored only in this browser, not synced. Clearing browser data removes them.</p>
          <div id="savedStatus" role="status">{savedStatus}</div>
        </details>
      </div>

      <details open>
        <summary>Controls (updated by template)</summary>
        <div id="sliders">
          {#each SLIDERS as [key, name] (key)}
            <div class="slider">
              <label for="s-{key}">{name}</label><input
                type="range"
                id="s-{key}"
                min="0"
                max="1"
                step="0.05"
                value={controls?.[key]}
                disabled={disabled.settings}
                oninput={(e) => setControl(key, e.currentTarget.valueAsNumber)}
              /><span id="v-{key}" class="hint">{controls ? percent(controls[key]) : ''}</span>
            </div>
          {/each}
        </div>
      </details>

      <div class="row">
        <div>
          <label for="previewStart">Preview start (seconds)</label><input
            type="number"
            id="previewStart"
            min="0"
            max="86400"
            step="0.1"
            disabled={disabled.queue}
            bind:value={previewStart}
          />
        </div>
        <div>
          <label for="previewLength">Preview length</label><select
            id="previewLength"
            disabled={disabled.queue}
            bind:value={previewLength}
          >
            <option value="10">10 seconds</option>
            <option value="15">15 seconds</option>
            <option value="20">20 seconds</option>
          </select>
        </div>
      </div>
      <button class="btn secondary" id="suggestBtn" disabled={disabled.run} onclick={() => runSelected('analyze')}
        >Suggest a template</button
      >
      <button class="btn secondary" id="previewBtn" disabled={disabled.run} onclick={() => runSelected('preview')}
        >Preview this section</button
      >
      <div id="suggestion" class="status" aria-live="polite">{suggestion}</div>
      <button
        class="btn secondary"
        id="applySuggestion"
        hidden={!suggestionKey}
        disabled={busy}
        onclick={applySuggestion}>Apply suggested template</button
      >
      <p class="hint">
        Suggestions and previews use the selected section. Short files use the available audio. Video previews are
        audio-only.
      </p>
      <button class="btn" id="cleanBtn" disabled={disabled.run} onclick={() => runSelected('clean')}
        >Process selected full file</button
      >
      <div class="progress" hidden={!progVisible} id="prog"><div style:width="{progress}%"></div></div>
      <div class="status" class:error={statusError} id="cleanStatus" aria-live="polite">{status}</div>
    </div>

    <div class="card" id="result" hidden={!shown}>
      <h2 id="resultTitle">{shown ? resultTitle(shown.name, shown.result) : 'Compare'}</h2>
      <p id="resultSettings" class="hint">{shown ? resultSettings(shown.label, shown.result) : ''}</p>
      <p id="matchNote" class="hint">{shown?.result.matching.note ?? ''}</p>
      <div role="group" aria-label="Choose comparison version">
        <button class="btn secondary" id="abBefore" aria-pressed={activeTrack === 0} onclick={() => chooseTrack(0)}
          >A: Original</button
        >
        <button class="btn secondary" id="abAfter" aria-pressed={activeTrack === 1} onclick={() => chooseTrack(1)}
          >B: Cleaned</button
        >
        <button class="btn" id="abPlay" onclick={togglePlay}>{playLabel}</button>
      </div>
      <label for="abSeek">Playback position <span id="abTime" class="hint">{abTime}</span></label>
      <input
        type="range"
        id="abSeek"
        min="0"
        max={seekMax}
        step="0.05"
        value={seekValue}
        oninput={(e) => seek(Number(e.currentTarget.value))}
      />
      {#if shown}
        {#key shown.id}
          {@render track('beforeMedia', 'compare-before', shown.job, 0)}
          {@render track('afterMedia', 'compare-after', shown.job, 1)}
        {/key}
      {:else}
        <div id="beforeMedia" hidden></div>
        <div id="afterMedia" hidden></div>
      {/if}
      <div id="abStatus" class="status" aria-live="polite">{abStatus}</div>
      <div id="resultNotes" role="status">
        {#if shown}
          {#each shown.result.warnings as warning, i (i)}
            <p>{warning}</p>
          {/each}
          <p class="hint">{scopeNote(shown.result.after)}</p>
        {/if}
      </div>
      <table id="metrics">
        {#if shown}
          <thead><tr><th>Measure</th><th>Before</th><th>Exported result</th></tr></thead>
          <tbody>
            {#each rows as row (row.label)}
              <tr><td>{row.label}</td><td>{row.before}</td><td class={row.tone}>{row.after}</td></tr>
            {/each}
          </tbody>
        {/if}
      </table>
      <a class="btn" id="download" download href={shown ? `/api/jobs/${shown.job}/result` : undefined}
        >{shown?.result.mode === 'preview' ? 'Download preview audio' : 'Download full natural version'}</a
      >
    </div>
  </div>

  <div id="panel-speak" role="tabpanel" aria-labelledby="tab-speak" hidden={tab !== 'speak'}>
    <div class="card">
      <p class="hint">
        Quick single-voice speech. For multi-voice scripts, captions and delivery loudness, use <a
          href="/studio"
          data-sveltekit-reload>Studio</a
        >. Cloned voices take about 10 seconds per second of speech on this Mac.
      </p>
      <label for="text">What should it say?</label>
      <textarea id="text" bind:value={text}></textarea>
      <div class="row">
        <div>
          <label for="voice">Voice</label><select id="voice" bind:value={voice}>
            {#if groups}
              {#each groups as g (g.label)}
                <optgroup label={g.label}>
                  {#each g.voices as v (v.id)}
                    <option value={v.id}>{v.text}</option>
                  {/each}
                </optgroup>
              {/each}
            {:else}
              <option>af_heart</option>
            {/if}
          </select>
        </div>
        <div>
          <label for="speed">Speed <span class="hint" id="speedVal">{speed.toFixed(2)}×</span></label><input
            type="range"
            id="speed"
            min="0.7"
            max="1.3"
            step="0.05"
            bind:value={speed}
          />
        </div>
        <div>
          <label for="engine">Engine</label>
          <select id="engine" bind:value={engine}>
            <option value="kokoro">Free, offline</option>
            <option value="elevenlabs">ElevenLabs (API key)</option>
            <option value="openai">OpenAI (API key)</option>
          </select>
        </div>
      </div>
      <button class="btn" id="speakBtn" disabled={speaking} onclick={speak}>Create voice</button>
      <div class="status" class:error={speakError} id="speakStatus" aria-live="polite">{speakStatus}</div>
      <div id="speakOut" hidden={!speakUrl}>
        <audio id="speakAudio" controls bind:this={speakAudio}></audio>
        <a class="btn secondary" id="speakDl" download="natural-voice.wav" href={speakUrl}>Download</a>
      </div>
    </div>
  </div>
</div>

<style>
  .clean {
    max-width: 860px;
    margin: 0 auto;
    --muted: #66706a;
  }
  @media (prefers-color-scheme: dark) {
    .clean {
      --muted: #9aa59e;
      --line: #2c3530;
    }
  }
  header h1 {
    margin: 0;
    font-size: 1.6rem;
    letter-spacing: -0.01em;
  }
  header p {
    margin: 4px 0 20px;
    color: var(--muted);
  }
  .tabs {
    display: flex;
    gap: 4px;
    border-bottom: 1px solid var(--line);
    margin-bottom: 20px;
  }
  .tabs button {
    background: none;
    border: 0;
    padding: 10px 14px;
    font: inherit;
    color: var(--muted);
    border-bottom: 2px solid transparent;
    cursor: pointer;
  }
  .tabs button[aria-selected='true'] {
    color: var(--ink);
    border-color: var(--accent);
    font-weight: 600;
  }
  label {
    display: block;
    font-weight: 600;
    margin-bottom: 6px;
  }
  textarea,
  select,
  input[type='number'],
  input[type='text'] {
    width: 100%;
    font: inherit;
    padding: 10px 12px;
    border: 1px solid var(--line);
    border-radius: 8px;
    background: var(--bg);
    color: var(--ink);
  }
  textarea {
    min-height: 140px;
    resize: vertical;
  }
  .row {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 14px;
    margin-top: 14px;
  }
  .templates {
    margin-top: 16px;
  }
  .drop {
    border: 2px dashed var(--line);
    border-radius: 12px;
    padding: 32px 16px;
    text-align: center;
    cursor: pointer;
    transition: border-color var(--motion-fast) var(--motion-easing);
  }
  .drop:hover,
  .drop.over,
  .drop:focus-visible {
    border-color: var(--accent);
    outline: none;
  }
  .drop strong {
    display: block;
    font-size: 1.05rem;
  }
  .btn {
    border: 0;
    padding: 11px 18px;
    margin-top: 16px;
  }
  .btn.secondary {
    border: 1px solid var(--line);
  }
  details {
    margin-top: 14px;
  }
  summary {
    cursor: pointer;
    color: var(--muted);
  }
  .slider {
    display: grid;
    grid-template-columns: 150px 1fr 40px;
    align-items: center;
    gap: 10px;
    margin-top: 8px;
  }
  .slider label {
    margin: 0;
    font-weight: 500;
  }
  input[type='range'] {
    width: 100%;
    accent-color: var(--accent);
  }
  .progress {
    height: 8px;
    background: var(--line);
    border-radius: 99px;
    overflow: hidden;
    margin-top: 14px;
  }
  .progress div {
    height: 100%;
    background: var(--accent);
    width: 0;
    transition: width var(--motion-progress) var(--motion-easing);
  }
  .status {
    color: var(--muted);
    margin-top: 8px;
    min-height: 1.5em;
  }
  .error {
    color: var(--bad);
  }
  @media (max-width: 600px) {
    .slider {
      grid-template-columns: 110px 1fr 36px;
    }
  }
  audio {
    width: 100%;
    margin-top: 6px;
    border-radius: 8px;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    margin-top: 12px;
    font-size: 0.95rem;
  }
  th,
  td {
    text-align: left;
    padding: 8px 6px;
    border-bottom: 1px solid var(--line);
  }
  .good {
    color: var(--good);
    font-weight: 600;
  }
  .worse {
    color: var(--bad);
  }
  h2 {
    font-size: 1.15rem;
    margin: 16px 0 8px;
  }
  #queueList {
    padding-left: 24px;
    overflow-wrap: anywhere;
  }
  #queueList li {
    margin: 8px 0;
  }
  #queueList button,
  #queueList a {
    margin-left: 8px;
  }
  #resultTitle,
  #resultSettings {
    overflow-wrap: anywhere;
  }
  #abSeek {
    margin-top: 8px;
  }
  #resultNotes p {
    margin: 8px 0;
  }
  button[aria-pressed='true'] {
    border: 2px solid var(--accent);
  }
  .clean :focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 3px;
  }
</style>
