<script lang="ts">
  import { tick, untrack } from 'svelte';
  import { api, errorText, sendJson } from '#lib/studio/api.ts';
  import { DELIVERY, lineWarnings, signed, styleDesc, uid } from '#lib/studio/logic.ts';
  import type { Studio } from '#lib/studio/studio.svelte.ts';
  import type { Line, NoteResult, Style } from '#lib/studio/types.ts';
  import RewritePanel from './RewritePanel.svelte';
  import VoiceSelect from './VoiceSelect.svelte';

  let { studio, line, index }: { studio: Studio; line: Line; index: number } = $props();

  const n = $derived(index + 1);
  const lines = $derived(studio.project.lines);
  let textarea: HTMLTextAreaElement | undefined = $state();
  let audio: HTMLAudioElement | undefined = $state();
  let takeBox: HTMLDivElement | undefined = $state();
  let audioSrc = $state(untrack(() => studio.previews.get(line.id) ?? ''));
  let error = $state('');
  let previewing = $state(false);
  let playingTake = $state<number | null>(null);
  let rewriteOpen = $state(0);
  let rewriteButton: HTMLButtonElement | undefined = $state();
  let pending = $state<NoteResult | null>(null);
  let noteMessage = $state('');

  const warnings = $derived(lineWarnings(line.text));
  const isClone = $derived(line.voice.startsWith('clone:'));
  const inLib = $derived(
    line.delivery === 'custom' && line.style ? studio.myStyles.find((m) => m.id === line.style?.id) : undefined,
  );
  const deliveryValue = $derived(line.delivery === 'custom' ? (inLib ? 'style:' + inLib.id : 'custom') : line.delivery);
  const deliveryHint = $derived(
    line.delivery === 'custom' && line.style ? styleDesc(line.style) : (studio.deliveryInfo[line.delivery] ?? ''),
  );

  function move(d: number): boolean {
    const i = lines.indexOf(line);
    const j = i + d;
    if (i < 0 || j < 0 || j >= lines.length) return false;
    [lines[i], lines[j]] = [lines[j], lines[i]];
    return true;
  }

  function duplicate() {
    const copy = { ...$state.snapshot(line), id: uid() };
    lines.splice(lines.indexOf(line) + 1, 0, copy);
    void studio.focusLine(copy.id);
  }

  async function remove() {
    const k = lines.indexOf(line);
    lines.splice(k, 1);
    const next = lines[Math.min(k, lines.length - 1)];
    if (next) void studio.focusLine(next.id);
    else {
      await tick();
      document.getElementById('add')?.focus();
    }
  }

  async function play(body: Line): Promise<string> {
    const r = await api('/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ line: body, dictionary: studio.payload().dictionary, polish: studio.opts.polish }),
    });
    return URL.createObjectURL(await r.blob());
  }

  async function show(url: string) {
    audioSrc = url;
    await tick();
    audio?.play().catch(() => {});
  }

  async function preview() {
    if (!line.text.trim()) {
      error = 'Type something to preview.';
      return;
    }
    error = '';
    previewing = true;
    try {
      const url = await play($state.snapshot(line));
      const old = studio.previews.get(line.id);
      if (old) URL.revokeObjectURL(old);
      studio.previews.set(line.id, url);
      await show(url);
    } catch (e) {
      error = errorText(e);
    } finally {
      previewing = false;
    }
  }

  async function playTake(t: number) {
    if (!line.text.trim()) {
      error = 'Type something first.';
      return;
    }
    error = '';
    playingTake = t;
    try {
      await show(await play({ ...$state.snapshot(line), take: t }));
    } catch (e) {
      error = errorText(e);
    } finally {
      playingTake = null;
    }
  }

  async function newTake() {
    // Each take is a seed for natural variation plus a tiny voice-style perturbation.
    const t = (crypto.getRandomValues(new Uint32Array(1))[0] % 2147483646) + 1;
    line.takes.push(t);
    await playTake(t);
    takeBox?.querySelector<HTMLButtonElement>('button[aria-label^="New take"]')?.focus();
  }

  function onVoice(value: string) {
    line.voice = value;
  }

  function onDelivery(value: string) {
    if (value.startsWith('style:')) {
      const m = studio.myStyles.find((x) => 'style:' + x.id === value);
      if (!m) return;
      // A style applies by value: its recipe and pause; the line's own speed, pitch and volume reset.
      line.delivery = 'custom';
      line.style = { ...m };
      line.speed = 1;
      line.pitch = 0;
      line.volume = 0;
      line.pause = m.pause_after;
      return;
    }
    if (value !== 'custom') {
      line.delivery = value;
      line.style = null;
    }
  }

  async function saveStyle() {
    const name = (prompt('Name this style (e.g. "Promo read"):', '') || '').trim();
    if (!name) return;
    try {
      const rec = await sendJson<Style>('/styles', { name: name.slice(0, 60), line: $state.snapshot(line) });
      studio.myStyles.push(rec);
      line.delivery = 'custom';
      line.style = { ...rec };
      line.speed = 1;
      line.pitch = 0;
      line.volume = 0;
      studio.say('proj', `Saved style “${rec.name}”. It's in the delivery picker under My styles.`);
    } catch (e) {
      error = errorText(e);
    }
  }

  async function interpret() {
    if (!(line.note ?? '').trim()) {
      pending = null;
      noteMessage = 'Write a note first, e.g. “slower, deeper, dramatic pause”.';
      return;
    }
    try {
      pending = await sendJson<NoteResult>('/note', { note: line.note, line: $state.snapshot(line) });
      noteMessage = '';
    } catch (e) {
      pending = null;
      noteMessage = errorText(e);
    }
  }

  function applyNote() {
    const p = pending;
    if (!p) return;
    Object.assign(line, { speed: p.speed, pitch: p.pitch, volume: p.volume, pause: p.pause, text: p.text });
    if (p.delivery !== line.delivery && p.delivery !== 'custom') {
      line.delivery = p.delivery;
      line.style = null;
    }
    pending = null;
    noteMessage = '';
    void studio.focusLine(line.id, `#note-${CSS.escape(line.id)}`);
    studio.say('proj', `Applied the note to line ${n}. You can still adjust every slider.`);
  }

  function insertTag(t: string) {
    const ta = textarea;
    if (!ta) return;
    const a = ta.selectionStart ?? ta.value.length,
      b = ta.selectionEnd ?? a;
    const pre = ta.value.slice(0, a);
    const ins = (pre && !/\s$/.test(pre) ? ' ' : '') + `[${t}] `;
    line.text = pre + ins + ta.value.slice(b);
    ta.value = line.text;
    ta.focus();
    ta.selectionStart = ta.selectionEnd = a + ins.length;
  }

  function numberOrNull(raw: string, lo: number, hi: number): number | null {
    const v = Number(raw);
    return raw !== '' && v >= lo && v <= hi ? v : null;
  }

  function onKey(e: KeyboardEvent) {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (!previewing) void preview();
      return;
    }
    if (!e.altKey || (e.key !== 'ArrowUp' && e.key !== 'ArrowDown')) return;
    e.preventDefault();
    if (move(e.key === 'ArrowUp' ? -1 : 1)) void studio.focusLine(line.id);
  }

  type Slider = {
    label: string;
    key: 'speed' | 'pitch' | 'volume' | 'pause';
    min: number;
    max: number;
    step: number;
    unit: string;
  };
  const SLIDERS: Slider[] = [
    { label: 'Speed', key: 'speed', min: 0.5, max: 2, step: 0.05, unit: '×' },
    { label: 'Pitch', key: 'pitch', min: -4, max: 4, step: 0.5, unit: ' st' },
    { label: 'Volume', key: 'volume', min: -24, max: 12, step: 0.5, unit: ' dB' },
    { label: 'Pause after', key: 'pause', min: 0, max: 10, step: 0.1, unit: ' s' },
  ];
</script>

<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
<article class="linecard" data-id={line.id} aria-label={`Line ${n}`} onkeydown={onKey}>
  <header>
    <label for={`text-${line.id}`}>Line {n}</label>
    <div class="row">
      <button
        type="button"
        class="btn secondary small"
        aria-label={`Move line ${n} up`}
        onclick={() => {
          if (move(-1)) void studio.focusLine(line.id, '[aria-label^="Move"][aria-label$="up"]');
        }}>↑</button
      >
      <button
        type="button"
        class="btn secondary small"
        aria-label={`Move line ${n} down`}
        onclick={() => {
          if (move(1)) void studio.focusLine(line.id, '[aria-label$="down"]');
        }}>↓</button
      >
      <button type="button" class="btn secondary small" aria-label={`Duplicate line ${n}`} onclick={duplicate}
        >Duplicate</button
      >
      <button type="button" class="btn danger small" aria-label={`Delete line ${n}`} onclick={() => void remove()}
        >Delete</button
      >
    </div>
  </header>
  <textarea
    id={`text-${line.id}`}
    maxlength="5000"
    placeholder="What this line says…"
    bind:this={textarea}
    bind:value={line.text}></textarea>
  <p class="warn">{warnings}</p>
  <div class="row" style="margin:8px 0">
    <input
      type="text"
      maxlength="60"
      placeholder="Speaker"
      aria-label={`Line ${n} speaker`}
      style="width:9em"
      bind:value={line.speaker}
    />
    <VoiceSelect catalog={studio.catalog} value={line.voice} label={`Line ${n} voice`} onchange={onVoice} />
    <select aria-label={`Line ${n} delivery`} value={deliveryValue} onchange={(e) => onDelivery(e.currentTarget.value)}>
      <optgroup label="Built-in">
        {#each Object.entries(DELIVERY) as [k, v] (k)}<option value={k} title={studio.deliveryInfo[k] ?? ''}>{v}</option
          >{/each}
      </optgroup>
      {#if studio.myStyles.length}
        <optgroup label="My styles">
          {#each studio.myStyles as m (m.id)}<option value={'style:' + m.id}>{m.name}</option>{/each}
        </optgroup>
      {/if}
      {#if line.delivery === 'custom' && line.style && !inLib}
        <optgroup label="In this project"
          ><option value="custom">{line.style.name} (saved with project)</option></optgroup
        >
      {/if}
    </select>
    <button
      type="button"
      class="btn secondary small"
      aria-label={`Preview line ${n}`}
      disabled={previewing}
      onclick={() => void preview()}>{previewing ? 'Rendering…' : '▶ Preview'}</button
    >
  </div>
  <span class="hint">{deliveryHint}</span>
  <div class="grid" style="margin-top:8px">
    {#each SLIDERS as s (s.key)}
      <div class="field">
        <label for={`${s.key}-${line.id}`}
          >{s.label}
          <span class="num">{s.key === 'pitch' && line.pitch > 0 ? '+' : ''}{line[s.key]}{s.unit}</span></label
        >
        <input
          type="range"
          id={`${s.key}-${line.id}`}
          min={s.min}
          max={s.max}
          step={s.step}
          value={line[s.key]}
          oninput={(e) => (line[s.key] = Number(e.currentTarget.value))}
        />
      </div>
    {/each}
  </div>
  <div class="row" style="margin-top:6px">
    <label for={`target-${line.id}`}>Fit this line to (s)</label>
    <input
      type="number"
      id={`target-${line.id}`}
      min="0.5"
      max="600"
      step="0.1"
      placeholder="natural"
      style="width:7em"
      value={line.target ? String(line.target) : ''}
      oninput={(e) => (line.target = e.currentTarget.value ? numberOrNull(e.currentTarget.value, 0.5, 600) : null)}
    />
    <span class="hint">optional, for dubbing</span>
  </div>
  <div class="row timed-only" style="margin-top:6px" hidden={studio.project.mode !== 'timed'}>
    {#each ['start', 'end'] as const as key (key)}
      <label for={`${key}-${line.id}`}>{key === 'start' ? 'Starts at (s)' : 'Ends by (s)'}</label>
      <input
        type="number"
        id={`${key}-${line.id}`}
        min="0"
        max="86400"
        step="0.01"
        placeholder={key === 'end' ? 'next start' : 'after previous'}
        style="width:8em"
        value={line[key] != null ? String(line[key]) : ''}
        oninput={(e) => (line[key] = numberOrNull(e.currentTarget.value, 0, 86400))}
      />
    {/each}
  </div>
  <div>
    <div class="row" style="margin-top:8px">
      <button
        type="button"
        class="btn secondary small"
        aria-label={`Save line ${n} settings as a style`}
        onclick={() => void saveStyle()}>Save as my style</button
      >
      <button
        type="button"
        class="btn secondary small"
        aria-label={`Rewrite line ${n} for speech`}
        bind:this={rewriteButton}
        onclick={() => (rewriteOpen += 1)}>Rewrite for speech</button
      >
    </div>
    {#if rewriteOpen}
      {#key rewriteOpen}
        <div>
          <RewritePanel
            text={line.text}
            status={studio.rewriteStatus}
            onaccept={(t) => {
              line.text = t;
              rewriteOpen = 0;
              rewriteButton?.focus();
            }}
            onclose={() => {
              rewriteOpen = 0;
              rewriteButton?.focus();
            }}
          />
        </div>
      {/key}
    {/if}
  </div>
  <div style="margin-top:8px">
    <label for={`note-${line.id}`}>Director's note</label>
    <div class="row">
      <input
        type="text"
        id={`note-${line.id}`}
        maxlength="200"
        placeholder="e.g. warm, slightly amused, slow down at the end"
        style="flex:1 1 16em"
        bind:value={() => line.note ?? '', (v) => (line.note = v)}
      />
      <button
        type="button"
        class="btn secondary small"
        aria-label={`Interpret director's note for line ${n}`}
        onclick={() => void interpret()}>What does this mean?</button
      >
      <button
        type="button"
        class="btn small"
        hidden={!pending?.understood.length}
        aria-label={`Apply director's note to line ${n}`}
        onclick={applyNote}>Apply</button
      >
    </div>
    <div class="hint" role="status" aria-live="polite">
      {#if pending}
        {@const d = pending}
        <strong>What I understood: </strong>{d.understood.length ? d.understood.join('; ') : 'nothing I can use'}.
        <br />Result: speed {d.speed}×, pitch {signed(d.pitch)} st, volume {signed(d.volume)} dB, pause after {d.pause} s,
        delivery {DELIVERY[d.delivery] || d.delivery}{d.tags.length
          ? `, adds ${d.tags.map((t) => '[' + t + ']').join(' ')}`
          : ''}.
        {#if d.unused.length}<br />Words I couldn't use: {d.unused.join(', ')}.{/if}
      {:else}
        {noteMessage}
      {/if}
    </div>
  </div>
  <div class="row" style="margin-top:6px" hidden={!isClone || !studio.cloneTags.length}>
    {#if isClone && studio.cloneTags.length}
      <span class="hint">Insert emotion:</span>
      {#each studio.cloneTags as t (t)}
        <button
          type="button"
          class="btn secondary small"
          aria-label={`Insert [${t}] into line ${n}`}
          onclick={() => insertTag(t)}>[{t}]</button
        >
      {/each}
    {/if}
  </div>
  <div class="takes" role="radiogroup" aria-label={`Line ${n} takes`} bind:this={takeBox}>
    <span class="hint">Takes:</span>
    {#each line.takes as t, k (k)}
      <label
        ><input
          type="radio"
          name={`take-${line.id}`}
          checked={line.take === t}
          aria-label={`Use take ${k + 1} for line ${n}`}
          onchange={() => (line.take = t)}
        />Take {k + 1}{t === 0 ? ' (original)' : ''}</label
      >
      <button
        type="button"
        class="btn secondary small"
        aria-label={`Play take ${k + 1} of line ${n}`}
        disabled={playingTake === t}
        onclick={() => void playTake(t)}>▶</button
      >
    {/each}
    <button
      type="button"
      class="btn secondary small"
      aria-label={`New take for line ${n}`}
      disabled={line.takes.length >= 5}
      title={line.takes.length >= 5 ? 'Five takes max. Pick one and start a new line to keep exploring.' : ''}
      onclick={() => void newTake()}>+ New take</button
    >
  </div>
  <audio controls hidden={!audioSrc} preload="none" src={audioSrc || undefined} bind:this={audio}></audio>
  <p class="err" role="alert">{error}</p>
</article>

<style>
  .linecard {
    border: 1px solid var(--line);
    border-radius: 10px;
    padding: 14px;
    margin-bottom: 12px;
    background: var(--bg);
  }
  .linecard:focus-within {
    border-color: var(--accent);
  }
  header {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 8px;
  }
  textarea {
    width: 100%;
    min-height: 70px;
    resize: vertical;
  }
  .warn {
    color: var(--warn);
    font-size: 0.9rem;
    margin: 6px 0 0;
  }
  .err {
    color: var(--bad);
    font-size: 0.9rem;
    margin: 6px 0 0;
  }
  .num {
    font-weight: 600;
    font-size: 0.95rem;
  }
  .takes {
    margin-top: 8px;
    display: flex;
    flex-wrap: wrap;
    gap: 6px 14px;
    align-items: center;
  }
  .takes label {
    font-weight: 500;
    display: inline-flex;
    gap: 4px;
    align-items: center;
  }
  @media (max-width: 560px) {
    .linecard .row > :global(select),
    .linecard .row > input {
      flex: 1 1 100%;
    }
  }
</style>
