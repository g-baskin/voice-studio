<script lang="ts">
  import { onDestroy, onMount, tick } from 'svelte';
  import { cloneApi, errorMessage } from '#lib/voicelab/http.ts';
  import { Recorder, UrlSlots, type Take } from '#lib/voicelab/recorder.ts';
  import { CLONE_SCRIPT, fmt, insertTag, PREVIEW_MAX } from '#lib/voicelab/text.ts';
  import type { CatalogVoice, CloneJob, CloneLanguage, CloneStatus } from '#lib/voicelab/types.ts';

  /** A message line whose class mirrors the old panel ('status', 'error' or 'status rec'). */
  type Line = { text: string; cls: string };
  const line = (text = '', cls = 'status'): Line => ({ text, cls });

  const urls = new UrlSlots();
  let destroyed = false;

  // Engine
  let engineOk = $state(false);
  let warm = false;
  let engine = $state<Line>(line('Checking the cloning engine…'));
  let notInstalled = $state(false);

  // Reference
  let source = $state(0);
  const sourceTabs: HTMLButtonElement[] = $state([]);
  let blob = $state<Blob | null>(null);
  let blobName = '';
  let fileInput: HTMLInputElement | undefined = $state();
  let fileInfo = $state('WAV, MP3, M4A, MP4, WebM or OGG, 5 to 60 seconds, up to 50 MB.');
  const recorder = new Recorder();
  let recording = $state(false);
  let recorded = $state(false);
  let clock = $state('0:00');
  let recMsg = $state<Line>(line());
  let recUrl = $state('');
  let name = $state('');
  let transcript = $state('');
  let consent = $state(false);
  let creating = $state(false);
  let createMsg = $state<Line>(line());

  const missing = $derived(
    [!blob && 'a recording', !name.trim() && 'a name', !consent && 'the consent checkbox'].filter(
      (m): m is string => !!m,
    ),
  );
  const why = $derived(
    !engineOk
      ? 'Install the cloning engine first.'
      : missing.length
        ? `Still needed: ${missing.join(', ')}.`
        : 'Ready.',
  );

  // Preview
  let clones = $state<CatalogVoice[]>([]);
  let voicesError = $state('');
  let cloneVoice = $state('');
  let previewText = $state('Hello! This is my cloned voice. How does it sound?');
  let previewEl: HTMLTextAreaElement | undefined = $state();
  let tags = $state<string[]>([]);
  let languages = $state<CloneLanguage[]>([{ code: 'en', name: 'English' }]);
  let language = $state('en');
  let previewing = $state(false);
  let prog = $state(0);
  let prevMsg = $state<Line>(line());
  let tagWarn = $state('');
  let playerUrl = $state('');

  // Voice changer
  let perf = $state<Blob | null>(null);
  let perfName = '';
  let perfUrl = $state('');
  let vcOrig: HTMLAudioElement | undefined = $state();
  const vcRecorder = new Recorder();
  let vcRecording = $state(false);
  let vcRecorded = $state(false);
  let vcClock = $state('0:00');
  let vcRecMsg = $state<Line>(line());
  let vcVoice = $state('');
  let vcConsent = $state(false);
  let vcBusy = $state(false);
  let vcProg = $state(0);
  let vcMsg = $state<Line>(line());
  let vcUrl = $state('');

  const vcMissing = $derived(
    [!perf && 'a performance', !vcVoice && 'a cloned voice', !vcConsent && 'the rights checkbox'].filter(
      (m): m is string => !!m,
    ),
  );
  const vcWhy = $derived(
    !engineOk
      ? 'Install the cloning engine first.'
      : vcMissing.length
        ? `Still needed: ${vcMissing.join(', ')}.`
        : 'Ready.',
  );

  function select(i: number) {
    source = i;
    blob = null;
    if (fileInput) fileInput.value = '';
    recUrl = '';
  }

  async function sourceKey(e: KeyboardEvent, i: number) {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    const j = (i + 1) % 2;
    select(j);
    await tick();
    sourceTabs[j]?.focus();
  }

  function fileChanged() {
    const f = fileInput?.files?.[0];
    blob = f ?? null;
    blobName = f ? f.name : '';
    fileInfo = f ? `Selected: ${f.name} (${(f.size / 1048576).toFixed(1)} MB)` : 'No file chosen.';
  }

  const UNSUPPORTED = 'This browser cannot record audio. Upload a file instead.';

  async function record() {
    if (recorder.recording) return recorder.stop();
    const started = await recorder.start(
      'recording',
      (c) => (clock = c),
      (take: Take) => {
        recording = false;
        recorded = true;
        recUrl = urls.set('rec', take.blob);
        const secs = take.seconds;
        blob = secs < 5 ? null : take.blob;
        blobName = take.name;
        recMsg =
          secs < 5
            ? line(`Only ${secs.toFixed(0)} s recorded. Record at least 5 seconds.`, 'error')
            : line(`Recorded ${fmt(secs)}. Listen back, or record again.`);
      },
    );
    if (started !== 'ok') {
      recMsg = line(
        started === 'blocked'
          ? 'Microphone access was blocked. Allow it in the browser, or upload a file.'
          : UNSUPPORTED,
        'error',
      );
      return;
    }
    recording = true;
    recMsg = line('Recording… read the script above.', 'status rec');
  }

  async function create() {
    if (creating || missing.length || !engineOk || !blob) return;
    const fd = new FormData();
    fd.append('name', name.trim());
    fd.append('consent', 'true');
    fd.append('transcript', transcript.trim());
    fd.append('file', blob, blobName || 'reference.wav');
    creating = true;
    createMsg = line('Preparing the reference recording…');
    try {
      const rec = (await (await cloneApi('/api/clone/voices', { method: 'POST', body: fd })).json()) as {
        id: string;
        name: string;
        meta: { reference_seconds: number };
      };
      // Announce only once the new voice is selected, so "Preview it below" is true when it appears.
      await loadVoices(rec.id);
      await tick();
      createMsg = line(`Created “${rec.name}” from ${rec.meta.reference_seconds} s of audio. Preview it below.`);
      previewEl?.focus();
    } catch (e) {
      createMsg = line(errorMessage(e), 'error');
    }
    creating = false;
  }

  async function addTag(tag: string) {
    const at = previewEl?.selectionStart ?? previewText.length;
    const next = insertTag(previewText, at, previewEl?.selectionEnd ?? at, tag);
    if (!next) {
      prevMsg = line(`No room for another tag (${PREVIEW_MAX} characters max).`, 'error');
      return;
    }
    previewText = next.value;
    await tick();
    previewEl?.focus();
    previewEl?.setSelectionRange(next.caret, next.caret);
  }

  /** Polls a clone job each second until done, then returns its final status and audio. */
  async function follow(
    kind: 'preview' | 'convert',
    job: string,
    onProgress: (s: CloneJob, elapsed: number) => void,
  ): Promise<{ s: CloneJob; audio: Blob }> {
    const t0 = Date.now();
    for (;;) {
      await new Promise((r) => setTimeout(r, 1000));
      if (destroyed) throw new Error('Stopped.');
      const s = (await (await cloneApi(`/api/clone/${kind}/${job}`)).json()) as CloneJob;
      if (s.status === 'error') throw new Error(s.error);
      if (s.status === 'done') return { s, audio: await (await cloneApi(`/api/clone/${kind}/${job}/audio`)).blob() };
      onProgress(s, Math.round((Date.now() - t0) / 1000));
    }
  }

  async function preview() {
    const text = previewText.trim();
    if (!cloneVoice) {
      prevMsg = line('Create or choose a cloned voice first.', 'error');
      return;
    }
    if (!text) {
      prevMsg = line('Type some text to preview.', 'error');
      previewEl?.focus();
      return;
    }
    const fd = new FormData();
    fd.append('voice', cloneVoice);
    fd.append('text', text);
    fd.append('language', language);
    previewing = true;
    prog = 0;
    playerUrl = '';
    // ~2.5 words/s of speech; English renders ~4.5 s per second, other languages ~2.5 s; +~20 s when cold.
    const words = text.split(/\s+/).length;
    const est = Math.round((words / 2.5) * (language === 'en' ? 4.5 : 2.5) + 5 + (warm ? 0 : 20));
    prevMsg = line(
      `Rendering… about ${est} s (roughly 4–5 s of compute per second of speech${warm ? '' : ', plus ~20 s to load the engine'}).`,
    );
    try {
      const { job, warning } = (await (await cloneApi('/api/clone/preview', { method: 'POST', body: fd })).json()) as {
        job: string;
        warning?: string;
      };
      tagWarn = warning || '';
      const { s, audio } = await follow('preview', job, (s, elapsed) => {
        prog = s.progress || 0;
        prevMsg = line(`${s.step || 'Rendering'}… ${elapsed} s elapsed (estimate ~${est} s).`);
      });
      playerUrl = urls.set('preview', audio);
      prevMsg = line(`Done: ${s.seconds} s of speech in ${s.render_seconds} s.`);
      warm = true;
    } catch (e) {
      prevMsg = line(errorMessage(e), 'error');
    }
    previewing = false;
  }

  async function loadVoices(pick?: string) {
    try {
      const { catalog } = (await (await cloneApi('/api/voices')).json()) as { catalog: CatalogVoice[] };
      const list = catalog.filter((v) => v.kind === 'clone');
      const has = (id: string) => list.some((v) => v.id === id);
      clones = list;
      cloneVoice = pick && has(pick) ? pick : (list[0]?.id ?? '');
      if (!has(vcVoice)) vcVoice = list[0]?.id ?? '';
      voicesError = '';
    } catch (e) {
      voicesError = `Could not load voices: ${errorMessage(e)}`;
    }
  }

  function setPerf(b: Blob | null, n: string) {
    perf = b;
    perfName = n;
    if (b) perfUrl = urls.set('perf', b);
    else {
      urls.revoke('perf');
      perfUrl = '';
    }
  }

  function vcFileChanged(e: Event & { currentTarget: HTMLInputElement }) {
    const f = e.currentTarget.files?.[0];
    setPerf(f ?? null, f ? f.name : '');
  }

  async function vcRecord() {
    if (vcRecorder.recording) return vcRecorder.stop();
    const started = await vcRecorder.start(
      'performance',
      (c) => (vcClock = c),
      (take: Take) => {
        vcRecording = false;
        vcRecorded = true;
        if (take.seconds < 1) {
          vcRecMsg = line('Too short. Record at least 1 second.', 'error');
          setPerf(null, '');
          return;
        }
        vcRecMsg = line(`Recorded ${fmt(take.seconds)}.`);
        setPerf(take.blob, take.name);
      },
    );
    if (started !== 'ok') {
      vcRecMsg = line(
        started === 'blocked' ? 'Microphone access was blocked. Allow it, or upload a file.' : UNSUPPORTED,
        'error',
      );
      return;
    }
    vcRecording = true;
    vcRecMsg = line('Recording… perform your lines.', 'status rec');
  }

  async function convert() {
    if (vcBusy || vcMissing.length || !engineOk || !perf) return;
    const fd = new FormData();
    fd.append('voice', vcVoice);
    fd.append('consent', 'true');
    fd.append('file', perf, perfName || 'performance.wav');
    vcBusy = true;
    vcProg = 0;
    vcUrl = '';
    const dur = vcOrig && Number.isFinite(vcOrig.duration) ? vcOrig.duration : 10;
    const est = Math.round(dur * 3 + 5 + (warm ? 0 : 20));
    vcMsg = line(`Uploading and converting… about ${est} s.`);
    try {
      const { job } = (await (await cloneApi('/api/clone/convert', { method: 'POST', body: fd })).json()) as {
        job: string;
      };
      const { s, audio } = await follow('convert', job, (s, elapsed) => {
        vcProg = s.progress || 0;
        vcMsg = line(`${s.step || 'Converting'}… ${elapsed} s elapsed (estimate ~${est} s).`);
      });
      vcUrl = urls.set('convert', audio);
      vcMsg = line(`Done: ${s.seconds} s converted in ${s.render_seconds} s.`);
      warm = true;
    } catch (e) {
      vcMsg = line(errorMessage(e), 'error');
    }
    vcBusy = false;
  }

  function readLanguages(raw: unknown): CloneLanguage[] | null {
    if (!Array.isArray(raw)) return null;
    const out: CloneLanguage[] = [];
    for (const l of raw as unknown[]) {
      if (l && typeof l === 'object' && 'code' in l && typeof l.code === 'string') {
        const label: unknown = 'name' in l ? l.name : undefined;
        out.push({ code: l.code, name: String(label || l.code) });
      }
    }
    return out;
  }

  onMount(async () => {
    try {
      const s = (await (await cloneApi('/api/clone/status')).json()) as CloneStatus;
      engineOk = !!s.installed;
      warm = !!s.warm;
      const langs = readLanguages(s.languages);
      if (langs) {
        languages = langs;
        language = langs[0]?.code ?? '';
      }
      tags = Array.isArray(s.emotion_tags)
        ? (s.emotion_tags as unknown[]).filter((t): t is string => typeof t === 'string')
        : [];
      if (engineOk) {
        engine = line(
          `Engine: ${s.model} · ${s.license} licence · ${(s.sample_rate ?? 0) / 1000} kHz · ${(s.device ?? '').toUpperCase()}${s.warm ? ' · ready' : ' · loads on first use (~20 s)'}. English only.`,
        );
      } else {
        engine = line('The voice cloning engine is not installed.', 'error');
        notInstalled = true;
      }
    } catch (e) {
      engine = line(`Could not check the engine: ${errorMessage(e)}`, 'error');
    }
    void loadVoices();
  });

  onDestroy(() => {
    destroyed = true;
    recorder.dispose();
    vcRecorder.dispose();
    urls.dispose();
  });
</script>

<section id="clonePanel" class="card" aria-label="Clone a voice">
  <div class="card" aria-live="polite">
    <h2>Clone a voice</h2>
    <p class={engine.cls}>{engine.text}</p>
    {#if notInstalled}
      <p>In a terminal, in the app folder, run (one time, about 3.3 GB):</p>
      <pre class="script"><code>scripts/setup_clone_engine.sh</code></pre>
      <p class="hint">Then reload this page.</p>
    {/if}
  </div>

  <div class="card">
    <h3>1. Reference recording</h3>
    <div class="tabs" role="tablist" aria-label="Reference source">
      {#each ['Upload a file', 'Record now'] as label, i (label)}
        <button
          type="button"
          role="tab"
          class="btn secondary"
          aria-selected={source === i}
          aria-controls={i === 0 ? 'clonePaneUpload' : 'clonePaneRecord'}
          tabindex={source === i ? 0 : -1}
          bind:this={sourceTabs[i]}
          onclick={() => select(i)}
          onkeydown={(e) => void sourceKey(e, i)}>{label}</button
        >
      {/each}
    </div>
    <div id="clonePaneUpload" role="tabpanel" hidden={source !== 0}>
      <label for="cloneFile">Reference recording</label>
      <div>
        <input
          type="file"
          id="cloneFile"
          accept=".wav,.mp3,.m4a,.mp4,.webm,.ogg,audio/*"
          bind:this={fileInput}
          onchange={fileChanged}
        />
      </div>
      <p class="hint" id="cloneFileInfo">{fileInfo}</p>
    </div>
    <div id="clonePaneRecord" role="tabpanel" hidden={source !== 1}>
      <p class="hint">Read this aloud in your normal voice (about 20 seconds), in a quiet room:</p>
      <p class="script">{CLONE_SCRIPT}</p>
      <div class="row">
        <button type="button" class="btn" onclick={() => void record()}
          >{recording ? 'Stop recording' : recorded ? 'Record again' : 'Start recording'}</button
        >
        <span>Time <span class="timer" aria-live="off">{clock}</span><span class="hint"> (5–60 s)</span></span>
      </div>
      <p class={recMsg.cls} role="status">{recMsg.text}</p>
      <audio controls hidden={!recUrl} src={recUrl || undefined}></audio>
    </div>
    <div class="field">
      <label for="cloneName">Voice name</label>
      <input
        type="text"
        id="cloneName"
        maxlength="60"
        autocomplete="off"
        placeholder="e.g. My narration voice"
        bind:value={name}
      />
    </div>
    <div class="field">
      <label for="cloneTranscript">Transcript <span class="hint">(optional)</span></label>
      <textarea
        id="cloneTranscript"
        rows="2"
        maxlength="2000"
        placeholder="What is said in the recording (optional)"
        bind:value={transcript}></textarea>
    </div>
    <label class="consent" for="cloneConsent"
      ><input type="checkbox" id="cloneConsent" bind:checked={consent} /><span
        >I own this voice or have permission to clone it.</span
      ></label
    >
    <div class="row">
      <button
        type="button"
        class="btn"
        id="cloneCreate"
        disabled={creating || missing.length > 0 || !engineOk}
        onclick={() => void create()}>Create voice</button
      >
    </div>
    <p class="hint" id="cloneWhy">{why}</p>
    <p class={createMsg.cls} id="cloneCreateMsg" role="status">{createMsg.text}</p>
  </div>

  <div class="card">
    <h3>2. Preview</h3>
    <p class="hint" hidden={!voicesError && clones.length > 0}>
      {voicesError || 'No cloned voices yet. Create one above.'}
    </p>
    <div class="field">
      <label for="cloneVoice">Cloned voice</label>
      <select id="cloneVoice" bind:value={cloneVoice}>
        {#each clones as v (v.id)}<option value={v.id}>{v.name}</option>{/each}
      </select>
    </div>
    <div class="field">
      <label for="clonePreviewText">Test text <span class="hint">{previewText.length}/{PREVIEW_MAX}</span></label>
      <textarea id="clonePreviewText" rows="3" maxlength={PREVIEW_MAX} bind:value={previewText} bind:this={previewEl}
      ></textarea>
      <p class="hint" id="cloneTagHint">
        Emotion tags like [laugh] or [sigh] add that sound where they sit. Other [bracketed] text is removed.
      </p>
    </div>
    <div
      class="row tags"
      id="cloneTags"
      role="group"
      aria-label="Insert an emotion tag"
      hidden={!tags.length || language !== 'en'}
    >
      <span class="hint">Insert:</span>
      {#each tags as t (t)}
        <button type="button" class="btn secondary tag" data-tag={t} onclick={() => void addTag(t)}>{t}</button>
      {/each}
    </div>
    <div class="field">
      <label for="cloneLang">Language</label>
      <select id="cloneLang" bind:value={language}>
        {#each languages as l (l.code)}<option value={l.code}>{l.name}</option>{/each}
      </select>
      <p class="hint" id="cloneLangHint" hidden={language === 'en'}>
        Other languages: a built-in voice reads the text, then it is re-voiced as your clone. Pronunciation and rhythm
        come from the built-in voice; emotion tags are ignored.
      </p>
    </div>
    <div class="row">
      <button
        type="button"
        class="btn"
        id="clonePreview"
        disabled={previewing || !cloneVoice || !engineOk}
        onclick={() => void preview()}>Preview</button
      >
      <a class="btn secondary" id="cloneDownload" download="clone-preview.wav" hidden={!playerUrl} href={playerUrl}
        >Download WAV</a
      >
    </div>
    <progress max="1" value={prog} hidden={!previewing}></progress>
    <p class={prevMsg.cls} id="clonePreviewMsg" role="status">{prevMsg.text}</p>
    <p class="hint" id="cloneTagWarn" role="status" hidden={!tagWarn}>{tagWarn}</p>
    <audio controls id="clonePlayer" hidden={!playerUrl} src={playerUrl || undefined}></audio>
  </div>

  <div class="card">
    <h3>3. Voice changer</h3>
    <p class="hint">
      Perform the lines yourself (1–60 s). Your timing, intonation and emotion are kept; the voice becomes the cloned
      one.
    </p>
    <div class="field">
      <label for="vcFile">Performance recording</label>
      <div>
        <input type="file" id="vcFile" accept=".wav,.mp3,.m4a,.mp4,.webm,.ogg,audio/*" onchange={vcFileChanged} />
      </div>
    </div>
    <div class="row">
      <button type="button" class="btn secondary" id="vcRecord" onclick={() => void vcRecord()}
        >{vcRecording ? 'Stop recording' : vcRecorded ? 'Record again' : 'Record performance'}</button
      >
      <span>Time <span class="timer">{vcClock}</span></span>
    </div>
    <p class={vcRecMsg.cls} role="status">{vcRecMsg.text}</p>
    <p class="hint" hidden={!perfUrl}>Original</p>
    <audio controls id="vcOriginal" hidden={!perfUrl} src={perfUrl || undefined} bind:this={vcOrig}></audio>
    <div class="field">
      <label for="vcVoice">Target cloned voice</label>
      <select id="vcVoice" bind:value={vcVoice}>
        {#each clones as v (v.id)}<option value={v.id}>{v.name}</option>{/each}
      </select>
    </div>
    <label class="consent" for="vcConsent"
      ><input type="checkbox" id="vcConsent" bind:checked={vcConsent} /><span
        >I have the rights to this performance and permission to use the target voice.</span
      ></label
    >
    <div class="row">
      <button
        type="button"
        class="btn"
        id="vcConvert"
        disabled={vcBusy || vcMissing.length > 0 || !engineOk}
        onclick={() => void convert()}>Convert</button
      >
      <a class="btn secondary" id="vcDownload" download="voice-changer.wav" hidden={!vcUrl} href={vcUrl}>Download WAV</a
      >
    </div>
    <p class="hint" id="vcWhy">{vcWhy}</p>
    <progress max="1" value={vcProg} hidden={!vcBusy}></progress>
    <p class={vcMsg.cls} id="vcMsg" role="status">{vcMsg.text}</p>
    <p class="hint" hidden={!vcUrl}>Converted</p>
    <audio controls id="vcConverted" hidden={!vcUrl} src={vcUrl || undefined}></audio>
  </div>
</section>

<style>
  #clonePanel :global {
    .row {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      align-items: center;
      margin: 10px 0;
    }
    .field {
      display: flex;
      flex-direction: column;
      gap: 4px;
      margin: 12px 0;
    }
    textarea,
    input[type='text'] {
      width: 100%;
    }
    .script {
      background: var(--bg);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      margin: 8px 0;
    }
    .timer {
      font-variant-numeric: tabular-nums;
      font-weight: 700;
    }
    .tabs {
      display: flex;
      gap: 4px;
    }
    .tabs [aria-selected='true'] {
      box-shadow: inset 0 -2px 0 var(--accent);
    }
    progress {
      width: 100%;
    }
    audio {
      width: 100%;
      margin-top: 8px;
    }
    .consent {
      display: flex;
      gap: 8px;
      align-items: flex-start;
      font-weight: 600;
    }
    .consent input {
      width: 20px;
      height: 20px;
      margin-top: 2px;
      flex: none;
    }
    .rec {
      color: var(--bad);
    }
    .tags {
      gap: 6px;
      margin: 4px 0 8px;
    }
    .tags .btn {
      padding: 6px 10px;
      font-weight: 500;
      font-size: 0.9rem;
    }
  }
</style>
