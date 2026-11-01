<script lang="ts">
  import { tick } from 'svelte';
  import { genDetail, llmError, reachText } from '#lib/studio/api.ts';
  import { MAX_LINES, newLine, pickVoices } from '#lib/studio/logic.ts';
  import type { Studio } from '#lib/studio/studio.svelte.ts';
  import type { GenResult, GenSample, GenStatus, LlmStatus } from '#lib/studio/types.ts';
  import Status from './Status.svelte';
  import VoiceSelect from './VoiceSelect.svelte';

  let { studio, status, loaded }: { studio: Studio; status: GenStatus | null; loaded: boolean } = $props();

  type GenBody = { seconds: number } & Record<string, unknown>;

  // The status arrives once at boot; later changes come from Connect/Disconnect.
  let llmOverride = $state<LlmStatus | null>(null);
  const llm = $derived<LlmStatus>(llmOverride ?? status?.llm ?? {});
  const shown = $derived<GenStatus>(status ?? { kinds: { ad: 'Ad / commercial' }, tones: ['friendly'] });
  const min = $derived(shown.min_seconds ?? 10);
  const max = $derived(shown.max_seconds ?? 300);

  let speakers = $state(['Narrator']);
  let topic = $state('');
  let kind = $state('');
  let tone = $state('');
  let brief = $state('');
  let seconds = $state('30');
  let cta = $state('');
  let audience = $state('');
  let tags = $state(false);
  let busy = $state(false);
  let ctrl: AbortController | null = null;
  let result = $state<GenResult | null>(null);
  let cast = $state<Record<string, string>>({});
  let lastSeconds = $state<number | null>(null);
  let aiKey = $state('');
  let aiModel = $state('');
  let aiBusy = $state(false);
  let disconnecting = $state(false);
  let speakerBox: HTMLDivElement | undefined = $state();
  let addSpeaker: HTMLButtonElement | undefined = $state();
  let topicInput: HTMLInputElement | undefined = $state();
  let secondsInput: HTMLInputElement | undefined = $state();
  let keyInput: HTMLInputElement | undefined = $state();
  let writeButton: HTMLButtonElement | undefined = $state();

  const saved = $derived(!!llm.available && !!(llm.key_saved || llm.env_key));
  const names = $derived(result ? [...new Set(result.lines.map((l) => l.speaker))] : []);

  $effect(() => {
    const ks = Object.keys(shown.kinds ?? {});
    if (!ks.includes(kind)) kind = ks[0] ?? '';
    const ts = shown.tones ?? [];
    if (!ts.includes(tone)) tone = ts[0] ?? '';
  });

  async function focusLastSpeaker() {
    await tick();
    speakerBox?.querySelector<HTMLInputElement>('.row:last-child input')?.focus();
  }

  function add() {
    if (speakers.length >= 4) return;
    speakers.push(
      ['Narrator', 'Guest', 'Host', 'Caller'].find((n) => !speakers.includes(n)) || `Speaker ${speakers.length + 1}`,
    );
    void focusLastSpeaker();
  }

  function onKind() {
    const blank = speakers.every((n) => ['Narrator', 'Host', 'Guest', ''].includes(n.trim()));
    if (kind === 'dialogue' && speakers.length < 2 && blank) speakers = ['Host', 'Guest'];
    else if (kind !== 'dialogue' && blank && speakers.length === 2) speakers = ['Narrator'];
  }

  function applyLlm(L: LlmStatus) {
    llmOverride = L;
    if (studio.rewriteStatus) studio.rewriteStatus = { ...studio.rewriteStatus, llm: L };
  }

  async function connect(e: SubmitEvent) {
    e.preventDefault();
    const key = aiKey.trim();
    if (!key) {
      studio.say('ai', 'Paste your OpenRouter key first.', true);
      keyInput?.focus();
      return;
    }
    const body: { api_key: string; model?: string } = { api_key: key };
    if (aiModel.trim()) body.model = aiModel.trim();
    aiBusy = true;
    studio.say('ai', 'Checking the key with a tiny test request… (up to 30 s)');
    try {
      const r = await fetch('/api/llm/key', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!r.ok) throw new Error(await llmError(r));
      const L = (await r.json()) as LlmStatus;
      aiKey = '';
      applyLlm(L);
      studio.say('ai', `Connected via ${L.via}.`);
      studio.say('gen', `Connected via ${L.via}. Write script will now use it.`);
    } catch (err) {
      studio.say('ai', reachText(err), true);
    } finally {
      aiBusy = false;
    }
  }

  async function disconnect() {
    if (!confirm('Disconnect the AI and delete the saved key from this computer?')) return;
    disconnecting = true;
    try {
      const r = await fetch('/api/llm/key', { method: 'DELETE' });
      if (!r.ok) throw new Error(await llmError(r));
      applyLlm((await r.json()) as LlmStatus);
      studio.say('gen', 'Disconnected. The saved key was deleted; the built-in outline writer is used now.');
    } catch (err) {
      studio.say('gen', reachText(err), true);
    } finally {
      disconnecting = false;
    }
  }

  function showResult(R: GenResult) {
    const ns = [...new Set(R.lines.map((l) => l.speaker))];
    const prev = cast;
    const next = pickVoices(ns, studio.catalog, studio.project.cast);
    for (const n of ns) if (prev[n]) next[n] = prev[n];
    cast = next;
    result = R;
  }

  async function run() {
    const secs = Number(seconds);
    const who = [...new Set(speakers.map((n) => n.trim()).filter(Boolean))];
    if (!topic.trim()) {
      studio.say('gen', 'Say what the script is about first.', true);
      topicInput?.focus();
      return;
    }
    if (!(secs >= 10 && secs <= 300)) {
      studio.say('gen', 'Length must be between 10 and 300 seconds.', true);
      secondsInput?.focus();
      return;
    }
    if (!who.length) {
      studio.say('gen', 'Name at least one speaker.', true);
      return;
    }
    const useLlm = !!llm.available;
    const body: GenBody = {
      topic: topic.trim(),
      brief,
      kind,
      tone,
      seconds: secs,
      speakers: who,
      cta: cta.trim(),
      audience: audience.trim(),
      mode: useLlm ? 'auto' : 'template',
      emotion_tags: tags,
    };
    ctrl = new AbortController();
    busy = true;
    studio.say('gen', useLlm ? 'Writing with your language model… (up to a minute)' : 'Arranging your points…');
    const t0 = Date.now();
    const timer = setInterval(() => studio.say('gen', `Writing… ${Math.round((Date.now() - t0) / 1000)} s`), 1000);
    try {
      const r = await fetch('/api/scriptgen', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: ctrl.signal,
      });
      if (!r.ok) {
        const m = await genDetail(r);
        if (r.status === 429)
          throw new Error('The computer is busy with another job. Wait for it to finish, then try again.');
        if (r.status === 503)
          throw new Error(
            (m || 'The language model is not available.') + ' Try again, or reload to use the built-in outline writer.',
          );
        throw new Error(m || `The script writer failed (${r.status}).`);
      }
      const R = (await r.json()) as GenResult;
      lastSeconds = body.seconds;
      showResult(R);
      studio.say(
        'gen',
        `Wrote ${R.lines.length} lines in ${Math.max(1, Math.round((Date.now() - t0) / 1000))} s. Check them, then choose Use this script or Add to end.`,
      );
    } catch (e) {
      if (e instanceof DOMException && e.name === 'AbortError') studio.say('gen', 'Stopped. Nothing was changed.');
      else studio.say('gen', reachText(e), true);
    } finally {
      clearInterval(timer);
      ctrl = null;
      busy = false;
    }
  }

  async function sample() {
    try {
      const r = await fetch('/api/scriptgen/sample?kind=' + encodeURIComponent(kind));
      if (!r.ok) throw new Error('No sample for this type.');
      const s = (await r.json()) as GenSample;
      topic = s.topic || '';
      brief = (s.brief || '').split(/\s*;\s*/).join('\n');
      cta = s.cta || '';
      if (s.kind === 'dialogue' && speakers.length < 2) speakers = ['Host', 'Guest'];
      await run();
    } catch (e) {
      studio.say('gen', reachText(e), true);
    }
  }

  function renameSpeaker(k: number, value: string) {
    if (!result) return;
    const l = result.lines[k];
    l.speaker = value.trim() || 'Narrator';
    if (!cast[l.speaker]) cast[l.speaker] = pickVoices([l.speaker], studio.catalog, studio.project.cast)[l.speaker];
  }

  function insert(append: boolean) {
    const R = result;
    const rows = (R ? R.lines : []).filter((l) => l.text.trim());
    const project = studio.project;
    if (!R || !rows.length) {
      studio.say('gen', 'There are no lines to add.', true);
      return;
    }
    if (append && project.lines.length + rows.length > MAX_LINES) {
      studio.say('gen', 'That would go over 500 lines.', true);
      return;
    }
    if (
      !append &&
      studio.hasText() &&
      !confirm(`Replace your current ${project.lines.length} line(s) with this script?`)
    )
      return;
    const lines = rows.map((l) => newLine(cast[l.speaker] || 'af_heart', l.speaker, l.text.slice(0, 5000)));
    for (const [n, v] of Object.entries(cast)) project.cast[n.toLowerCase()] = v;
    if (!append) {
      project.lines = lines;
      if (R.title && (!project.title || project.title === 'Untitled project')) project.title = R.title.slice(0, 120);
    } else project.lines = project.lines.concat(lines);
    void studio.focusLine(lines[0].id);
    result = null;
    studio.say('gen', `${append ? 'Added' : 'Inserted'} ${lines.length} lines into the script below.`);
  }

  function discard() {
    result = null;
    studio.say('gen', 'Discarded. Your script is unchanged.');
    writeButton?.focus();
  }

  const off = $derived(busy || !status);
  const engineText = $derived(
    !loaded
      ? 'Checking for a language model…'
      : !status
        ? "Couldn't reach the script writer. Reload the page to try again."
        : llm.available
          ? `Using your language model (via ${llm.via}). Writing can take up to a minute.`
          : 'No AI connected. The built-in outline writer will arrange your points (a template, not an AI). Connect an AI for fully written scripts.',
  );
</script>

<section class="card" aria-labelledby="gen-h">
  <details id="gen-box">
    <summary id="gen-h">Write a script for me</summary>
    <p class="hint" class:error={loaded && !status} id="gen-engine" role="status">{engineText}</p>
    <div id="ai-connected" class="row" hidden={!saved}>
      <span id="ai-connected-text" class="wrapword"
        >{#if saved}{llm.env_key
            ? `Connected: ${llm.provider || 'OpenRouter'} (model ${llm.model}). The key comes from the OPENROUTER_API_KEY environment variable and can't be removed from here.`
            : `Connected: ${llm.provider || 'OpenRouter'} (key ${llm.key_hint}, model ${llm.model})`}{/if}</span
      >
      <button
        type="button"
        class="btn danger small"
        id="ai-disconnect"
        hidden={!!llm.env_key}
        disabled={disconnecting}
        onclick={() => void disconnect()}>Disconnect</button
      >
    </div>
    <details id="ai-box" hidden={!!llm.available}>
      <summary>Connect AI</summary>
      <p class="hint">
        Shark Audio uses OpenRouter, one key for many models. Get a key at
        <a href="https://openrouter.ai/keys" target="_blank" rel="noopener">https://openrouter.ai/keys</a>. Your key is
        stored only on this computer, in the app's data folder, and is never shown again.
      </p>
      <form id="ai-form" autocomplete="off" onsubmit={(e) => void connect(e)}>
        <div class="grid">
          <div class="field">
            <label for="ai-key">OpenRouter API key</label>
            <input
              id="ai-key"
              type="password"
              autocomplete="off"
              spellcheck="false"
              autocapitalize="off"
              placeholder="sk-or-…"
              disabled={aiBusy}
              bind:this={keyInput}
              bind:value={aiKey}
            />
          </div>
          <div class="field">
            <label for="ai-model">Model <span class="hint">optional</span></label>
            <input
              id="ai-model"
              type="text"
              autocomplete="off"
              spellcheck="false"
              maxlength="100"
              placeholder={llm.default_model || 'openai/gpt-4o-mini'}
              bind:value={aiModel}
            />
            <span class="hint">openai/gpt-4o-mini is cheap and good for scripts</span>
          </div>
        </div>
        <div class="row" style="margin-top:8px">
          <button class="btn" id="ai-connect" type="submit" disabled={aiBusy}>Connect</button>
        </div>
      </form>
      <Status id="ai-status" status={studio.status.ai} />
    </details>
    <div class="grid">
      <div class="field">
        <label for="gen-topic">What is it about</label><input
          id="gen-topic"
          type="text"
          maxlength="120"
          placeholder="e.g. a neighbourhood coffee shop's new oat latte"
          bind:this={topicInput}
          bind:value={topic}
        />
      </div>
      <div class="field">
        <label for="gen-kind">Type</label><select id="gen-kind" bind:value={kind} onchange={onKind}>
          {#each Object.entries(shown.kinds ?? {}) as [k, v] (k)}<option value={k}>{v}</option>{/each}
        </select>
      </div>
      <div class="field">
        <label for="gen-tone">Tone</label><select id="gen-tone" bind:value={tone}>
          {#each shown.tones ?? [] as t (t)}<option value={t}>{t[0].toUpperCase() + t.slice(1)}</option>{/each}
        </select>
      </div>
    </div>
    <div class="field" style="margin-top:10px">
      <label for="gen-brief">Details <span class="hint">one point per line</span></label>
      <textarea
        id="gen-brief"
        rows="4"
        maxlength="2000"
        placeholder={'open 7am to 7pm\noat milk at no extra cost\nfirst cup half price this week'}
        bind:value={brief}></textarea>
    </div>
    <fieldset class="plainset" style="margin-top:10px">
      <legend>Length <span class="hint" id="gen-len-hint">{min}–{max} s</span></legend>
      <div class="row" id="gen-quick">
        {#each [15, 30, 60, 90] as sec (sec)}
          <button
            type="button"
            class="btn secondary small"
            data-sec={sec}
            aria-pressed={Number(seconds) === sec}
            onclick={() => (seconds = String(sec))}>{sec} s</button
          >
        {/each}
        <label for="gen-seconds" class="hint">or seconds</label><input
          id="gen-seconds"
          type="number"
          {min}
          {max}
          step="5"
          style="width:6em"
          bind:this={secondsInput}
          value={seconds}
          oninput={(e) => (seconds = e.currentTarget.value)}
        />
      </div>
    </fieldset>
    <fieldset class="plainset" style="margin-top:10px">
      <legend>Who is speaking <span class="hint">up to 4</span></legend>
      <div id="gen-speakers" bind:this={speakerBox}>
        {#each speakers as _, k (k)}
          <div class="row" style="margin-bottom:6px">
            <input
              type="text"
              maxlength="40"
              aria-label={`Speaker ${k + 1} name`}
              style="width:12em"
              bind:value={speakers[k]}
            />
            <button
              type="button"
              class="btn danger small"
              aria-label={`Remove speaker ${k + 1}`}
              disabled={speakers.length < 2}
              onclick={() => {
                speakers.splice(k, 1);
                addSpeaker?.focus();
              }}>Remove</button
            >
          </div>
        {/each}
      </div>
      <button
        type="button"
        class="btn secondary small"
        id="gen-add-speaker"
        disabled={speakers.length >= 4}
        bind:this={addSpeaker}
        onclick={add}>+ Add speaker</button
      >
    </fieldset>
    <div class="grid" style="margin-top:10px">
      <div class="field">
        <label for="gen-cta">Call to action <span class="hint">optional</span></label><input
          id="gen-cta"
          type="text"
          maxlength="200"
          placeholder="e.g. Visit us on Main Street."
          bind:value={cta}
        />
      </div>
      <div class="field">
        <label for="gen-audience">Audience <span class="hint">optional</span></label><input
          id="gen-audience"
          type="text"
          maxlength="200"
          placeholder="e.g. commuters, students"
          bind:value={audience}
        />
      </div>
    </div>
    <label style="display:block;margin-top:10px"
      ><input type="checkbox" id="gen-tags" bind:checked={tags} /> Use emotion tags
      <span class="hint"
        >([chuckle], [sigh]…; they only sound in cloned voices, other voices would read them aloud)</span
      ></label
    >
    <div class="row" style="margin-top:12px">
      <button class="btn" id="gen-write" type="button" disabled={off} bind:this={writeButton} onclick={() => void run()}
        >Write script</button
      >
      <button class="btn secondary" id="gen-sample" type="button" disabled={off} onclick={() => void sample()}
        >Surprise me (test script)</button
      >
      <button class="btn danger" id="gen-cancel" type="button" hidden={!busy} onclick={() => ctrl?.abort()}
        >Stop writing</button
      >
    </div>
    <Status id="gen-status" status={studio.status.gen} />
    <div id="gen-result" hidden={!result}>
      {#if result}
        <div class="row" style="justify-content:space-between">
          <h3 id="gen-title" class="wrapword" style="font-size:1.05rem;margin:8px 0">
            {result.title || 'Untitled script'}
          </h3>
          <span class="badge" id="gen-badge"
            >{result.engine === 'language model'
              ? 'Written by your language model'
              : 'Built-in outline (template)'}</span
          >
        </div>
        <p class="meter" id="gen-length">
          About {result.estimated_seconds} s spoken ({result.words} words){lastSeconds
            ? `, target ${lastSeconds} s`
            : ''}.
        </p>
        <ul class="hint" id="gen-notes">
          {#each result.notes ?? [] as note, k (k)}<li>{note}</li>{/each}
        </ul>
        <div id="gen-lines">
          {#each result.lines as l, k (l)}
            <div class="genline">
              <input
                type="text"
                maxlength="40"
                aria-label={`Script line ${k + 1} speaker`}
                value={l.speaker}
                onchange={(e) => renameSpeaker(k, e.currentTarget.value)}
              />
              <textarea maxlength="5000" aria-label={`Script line ${k + 1} text`} rows="2" bind:value={l.text}
              ></textarea>
              <button
                type="button"
                class="btn danger small"
                aria-label={`Remove script line ${k + 1}`}
                onclick={() => result?.lines.splice(k, 1)}>Remove</button
              >
            </div>
          {:else}
            <p class="hint">All lines removed. Write another version, or Cancel.</p>
          {/each}
        </div>
        <h4 style="font-size:.95rem;margin:12px 0 6px">Cast</h4>
        <div id="gen-cast">
          {#each names as n (n)}
            <div class="row" style="margin-bottom:6px">
              <span class="wrapword" style="min-width:8em;font-weight:600">{n}</span>
              <VoiceSelect
                catalog={studio.catalog}
                value={cast[n] || 'af_heart'}
                label={`Voice for ${n}`}
                onchange={(v) => (cast[n] = v)}
              />
            </div>
          {/each}
        </div>
      {/if}
      <div class="row" style="margin-top:10px">
        <button class="btn" id="gen-use" type="button" disabled={busy} onclick={() => insert(false)}
          >Use this script</button
        >
        <button class="btn secondary" id="gen-append" type="button" disabled={busy} onclick={() => insert(true)}
          >Add to end</button
        >
        <button class="btn secondary" id="gen-again" type="button" disabled={busy} onclick={() => void run()}
          >Write another version</button
        >
        <button class="btn secondary" id="gen-close" type="button" onclick={discard}>Cancel</button>
      </div>
    </div>
  </details>
</section>

<style>
  .genline {
    display: grid;
    grid-template-columns: 9em 1fr auto;
    gap: 8px;
    margin-bottom: 6px;
    align-items: start;
  }
  .genline input,
  .genline textarea {
    width: 100%;
    min-width: 0;
  }
  .genline textarea {
    min-height: 2.6em;
    resize: vertical;
  }
  @media (max-width: 560px) {
    .genline {
      grid-template-columns: 1fr auto;
    }
    .genline input {
      grid-column: 1 / -1;
    }
  }
  .plainset {
    border: 0;
    padding: 0;
    margin-left: 0;
    margin-right: 0;
    min-width: 0;
  }
  .plainset legend {
    font-weight: 600;
    padding: 0;
    margin-bottom: 6px;
  }
  .badge {
    font-size: 0.8rem;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 99px;
    border: 1px solid var(--line);
    background: var(--bg);
  }
  #ai-box {
    margin-bottom: 10px;
  }
  #ai-box a {
    color: var(--accent);
    font-weight: 600;
    overflow-wrap: anywhere;
  }
  input[type='password'] {
    font: inherit;
    padding: 9px 11px;
    border: 1px solid var(--line);
    border-radius: 8px;
    background: var(--bg);
    color: var(--ink);
    max-width: 100%;
  }
</style>
