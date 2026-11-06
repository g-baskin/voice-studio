<script lang="ts">
  import { api, errorText, sendJson } from '#lib/studio/api.ts';
  import { MAX_LINES, normalLine } from '#lib/studio/logic.ts';
  import type { Studio } from '#lib/studio/studio.svelte.ts';
  import type { Line, ParseResult } from '#lib/studio/types.ts';
  import RewritePanel from './RewritePanel.svelte';
  import Status from './Status.svelte';
  import VoiceSelect from './VoiceSelect.svelte';

  let { studio }: { studio: Studio } = $props();

  let text = $state('');
  let parsed = $state<ParseResult | null>(null);
  let rewriteOpen = $state(0);
  let rewriteButton: HTMLButtonElement | undefined = $state();

  async function parse() {
    if (!text.trim()) {
      studio.say('paste', 'Paste a script first.', true);
      return;
    }
    studio.say('paste', 'Reading script…');
    try {
      const p = await sendJson<ParseResult>('/parse', { text, cast: studio.project.cast });
      parsed = p;
      studio.say(
        'paste',
        `${p.lines.length} lines, ${p.cast.length} speaker${p.cast.length === 1 ? '' : 's'}.` +
          (p.warnings.length ? ' ' + p.warnings.slice(0, 3).join(' ') : ''),
      );
    } catch (e) {
      studio.say('paste', errorText(e), true);
    }
  }

  function importParsed(append: boolean) {
    const p = parsed;
    if (!p) return;
    const project = studio.project;
    const map = Object.fromEntries(p.cast.map((c) => [c.speaker.toLowerCase(), c.voice]));
    for (const c of p.cast) if (c.speaker) project.cast[c.speaker.toLowerCase()] = c.voice;
    const lines = p.lines.map((l) => normalLine({ ...l, voice: map[l.speaker.toLowerCase()] || l.voice }));
    if (append && project.lines.length + lines.length > MAX_LINES) {
      studio.say('paste', 'That would go over 500 lines.', true);
      return;
    }
    if (!append && studio.hasText() && !confirm('Replace the current script with the pasted lines?')) return;
    project.lines = append ? project.lines.concat(lines) : lines;
    void studio.focusLine(lines[0]?.id);
    studio.say('paste', `Imported ${lines.length} lines.`);
  }

  async function subtitles(e: Event & { currentTarget: HTMLInputElement }) {
    const input = e.currentTarget;
    const f = input.files?.[0];
    if (!f) return;
    if (f.size > 2 * 1024 * 1024) {
      studio.say('paste', 'Subtitle file too large (2 MB max).', true);
      input.value = '';
      return;
    }
    if (studio.hasText() && !confirm('Replace the current script with the subtitle cues?')) {
      input.value = '';
      return;
    }
    const fd = new FormData();
    fd.append('file', f);
    studio.say('paste', 'Reading subtitles…');
    try {
      const voice = studio.project.lines[0]?.voice || 'af_heart';
      const r = (await (
        await api('/subtitles?voice=' + encodeURIComponent(voice), { method: 'POST', body: fd })
      ).json()) as { lines: Partial<Line>[]; warnings: string[] };
      studio.project.lines = r.lines.map(normalLine);
      studio.project.mode = 'timed';
      void studio.focusLine(studio.project.lines[0]?.id);
      studio.say(
        'paste',
        `Imported ${r.lines.length} timed lines; placement set to Timed.` +
          (r.warnings.length ? ' ' + r.warnings.slice(0, 3).join(' ') : ''),
      );
    } catch (err) {
      studio.say('paste', errorText(err), true);
    }
    input.value = '';
  }
</script>

<section class="card" aria-labelledby="paste-h">
  <details id="paste-box">
    <summary id="paste-h">Paste a script</summary>
    <p class="hint">
      One line per paragraph. Mark speakers as <code>NARRATOR: text</code> or <code>[Narrator] text</code>; untagged
      lines keep the last speaker.
    </p>
    <div class="field">
      <label for="paste">Script</label><textarea
        id="paste"
        rows="6"
        maxlength="50000"
        placeholder={'HOST: Welcome back to the show.\nGUEST: Thanks for having me.'}
        bind:value={text}></textarea>
    </div>
    <div class="row" style="margin-top:8px">
      <button class="btn secondary" id="parse" type="button" onclick={() => void parse()}>Find speakers</button>
      <button
        class="btn secondary"
        id="paste-rewrite"
        type="button"
        bind:this={rewriteButton}
        onclick={() => (rewriteOpen += 1)}>Rewrite for speech</button
      >
    </div>
    <div id="paste-rw-panel" hidden={!rewriteOpen}>
      {#if rewriteOpen}
        {#key rewriteOpen}
          <RewritePanel
            {text}
            status={studio.rewriteStatus}
            onaccept={(t) => {
              text = t;
              rewriteOpen = 0;
              rewriteButton?.focus();
            }}
            onclose={() => {
              rewriteOpen = 0;
              rewriteButton?.focus();
            }}
          />
        {/key}
      {/if}
    </div>
    <div id="cast" hidden={!parsed}>
      <h3 style="font-size:1rem">Cast: pick a voice for each speaker</h3>
      <div id="cast-rows">
        {#each parsed?.cast ?? [] as c, k (k)}
          <div class="row" style="margin-bottom:8px">
            <span class="wrapword" style="min-width:8em;font-weight:600">{c.speaker || '(no speaker)'}</span>
            <VoiceSelect
              catalog={studio.catalog}
              value={c.voice}
              label={`Voice for ${c.speaker || 'untagged lines'}`}
              onchange={(v) => (c.voice = v)}
            />
          </div>
        {/each}
      </div>
      <div class="row">
        <button class="btn" id="import" type="button" onclick={() => importParsed(false)}
          >Replace script with these lines</button
        >
        <button class="btn secondary" id="append" type="button" onclick={() => importParsed(true)}>Add to end</button>
      </div>
    </div>
    <Status id="paste-status" status={studio.status.paste} />
    <div class="field" style="margin-top:12px">
      <label for="subs"
        >Or import subtitles <span class="hint">.srt or .vtt · 2 MB max · switches to Timed placement</span></label
      >
      <input id="subs" type="file" accept=".srt,.vtt" onchange={(e) => void subtitles(e)} />
    </div>
  </details>
</section>
