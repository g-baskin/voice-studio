<script lang="ts">
  import { downloadSrt } from '#lib/editor/api.ts';
  import { DEFAULT_CAPTIONS, captionTrack } from '#lib/editor/captions.ts';
  import type { Editor } from '#lib/editor/editor.svelte.ts';
  import type { CaptionFont, CaptionStyle, Captions } from '#lib/editor/types.ts';

  let { editor }: { editor: Editor } = $props();

  const STYLES: { id: CaptionStyle; label: string; title: string }[] = [
    { id: 'pop', label: 'Pop', title: 'The spoken word grows and changes colour' },
    { id: 'karaoke', label: 'Karaoke', title: 'Words fill with colour as they are spoken' },
    { id: 'bold', label: 'Bold box', title: 'The spoken word sits in a coloured box' },
    { id: 'clean', label: 'Clean', title: 'Plain words on a dark band' },
  ];
  const FONTS: { id: CaptionFont; label: string }[] = [
    { id: 'sans-bold', label: 'Sans bold' },
    { id: 'impact', label: 'Impact' },
    { id: 'rounded', label: 'Rounded' },
    { id: 'system', label: 'Wide' },
  ];

  const caps = $derived<Captions>(editor.seq.captions ?? { ...DEFAULT_CAPTIONS, enabled: false });
  const on = $derived(!!editor.seq.captions?.enabled);
  // Sound tracks first, then picture tracks (a video clip keeps its sound until it is detached).
  const soundTracks = $derived([
    ...editor.seq.tracks.filter((t) => t.kind === 'audio'),
    ...editor.seq.tracks.filter((t) => t.kind === 'video'),
  ]);
  const following = $derived(captionTrack(editor.seq));
  const missing = $derived(
    [...new Set(editor.seq.clips.filter((c) => c.track === following).map((c) => c.media))].filter(
      (id) => editor.transcripts[id] === null,
    ),
  );
  let error = $state('');

  const set = (patch: Partial<Captions>) => editor.setCaptions(patch);
  const num = (e: Event) => Number((e.currentTarget as HTMLInputElement).value);
  const text = (e: Event) => (e.currentTarget as HTMLInputElement | HTMLSelectElement).value;

  async function srt() {
    error = '';
    try {
      await downloadSrt($state.snapshot(editor.seq));
    } catch (e) {
      error = e instanceof Error ? e.message : 'Could not make the SRT file.';
    }
  }
</script>

<h2>Captions <span class="sub">word by word, from transcripts</span></h2>
<label class="check switch"
  ><input type="checkbox" role="switch" checked={on} onchange={() => editor.toggleCaptions()} />Show captions (⇧C)</label
>

<fieldset disabled={!on}>
  <legend class="visually-hidden">Caption settings</legend>
  <label
    >Words from
    <select
      value={caps.track ?? ''}
      onchange={(e) => set({ track: text(e) || null })}
      aria-describedby={on && (missing.length || !following) ? 'caption-track-note' : undefined}
    >
      <option value="">First track with sound</option>
      {#each soundTracks as t (t.id)}<option value={t.id}>{t.name}</option>{/each}
    </select>
  </label>
  {#if on && missing.length}
    <p class="hint" id="caption-track-note">
      {missing.length === 1 ? 'A file' : `${missing.length} files`} on this track
      {missing.length === 1 ? 'has' : 'have'} no transcript yet. Transcribe {missing.length === 1 ? 'it' : 'them'}
      in the Transcript tab.
    </p>
  {:else if on && !following}
    <p class="hint" id="caption-track-note">Add a clip with sound to the timeline.</p>
  {/if}

  <div class="styles" role="group" aria-label="Caption style">
    {#each STYLES as st (st.id)}
      <button
        type="button"
        class="btn secondary small"
        aria-pressed={caps.style === st.id}
        title={st.title}
        onclick={() => set({ style: st.id })}>{st.label}</button
      >
    {/each}
  </div>

  <div class="row2">
    <label
      >Font
      <select value={caps.font} onchange={(e) => set({ font: text(e) as CaptionFont })}>
        {#each FONTS as f (f.id)}<option value={f.id}>{f.label}</option>{/each}
      </select>
    </label>
    <label
      >Words at once
      <input
        type="number"
        min="1"
        max="8"
        step="1"
        value={caps.words_per_page}
        onchange={(e) => set({ words_per_page: Math.round(Math.min(8, Math.max(1, num(e) || 3))) })}
      />
    </label>
    <label
      >Size {Math.round(caps.size * 100)}%
      <input
        type="range"
        min="0.03"
        max="0.15"
        step="0.005"
        value={caps.size}
        onchange={(e) => set({ size: num(e) })}
      />
    </label>
    <label
      >Height {Math.round(caps.y * 100)}%
      <input type="range" min="0.1" max="0.95" step="0.01" value={caps.y} onchange={(e) => set({ y: num(e) })} />
    </label>
    <label
      >Letters per line
      <input
        type="number"
        min="8"
        max="40"
        step="1"
        value={caps.max_chars}
        onchange={(e) => set({ max_chars: Math.round(Math.min(40, Math.max(8, num(e) || 24))) })}
      />
    </label>
    <label
      >Outline {Math.round(caps.stroke * 100)}%
      <input type="range" min="0" max="0.3" step="0.01" value={caps.stroke} onchange={(e) => set({ stroke: num(e) })} />
    </label>
    <label
      >Text colour
      <input type="color" value={caps.color} onchange={(e) => set({ color: text(e) })} />
    </label>
    <label
      >Spoken word
      <input type="color" value={caps.highlight} onchange={(e) => set({ highlight: text(e) })} />
    </label>
  </div>
  <label class="check"
    ><input type="checkbox" checked={caps.uppercase} onchange={() => set({ uppercase: !caps.uppercase })} />Capital
    letters</label
  >
  <label class="check"
    ><input type="checkbox" checked={caps.animate} onchange={() => set({ animate: !caps.animate })} />Animate the spoken
    word</label
  >
</fieldset>

<div class="actions">
  <button type="button" class="btn secondary small" disabled={!on} onclick={srt}>Download SRT</button>
</div>
{#if error}<p class="bad" role="alert">{error}</p>{/if}
<p class="hint">
  Captions show in the program viewer and are burned into exports. Premiere Pro XML does not carry them; use the SRT
  file there.
</p>

<style>
  fieldset {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin: 0;
    padding: 0;
    border: 0;
    min-width: 0;
  }
  fieldset:disabled {
    opacity: 0.55;
  }
  .styles {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }
  .styles [aria-pressed='true'] {
    color: var(--accent-ink);
    background: var(--accent);
    border-color: var(--accent);
  }
  input[type='range'] {
    width: 100%;
    accent-color: var(--accent);
  }
  input[type='color'] {
    width: 100%;
    height: 28px;
    padding: 0 2px;
    background: var(--bg);
    border: 1px solid var(--line);
    border-radius: 5px;
  }
  .visually-hidden {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
  }
</style>
