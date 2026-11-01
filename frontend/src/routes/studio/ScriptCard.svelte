<script lang="ts">
  import { MAX_LINES, newLine } from '#lib/studio/logic.ts';
  import type { Studio } from '#lib/studio/studio.svelte.ts';
  import LineCard from './LineCard.svelte';

  let { studio }: { studio: Studio } = $props();

  const lines = $derived(studio.project.lines);
  const count = $derived(
    `${lines.length} line${lines.length === 1 ? '' : 's'} · ${lines.reduce((n, l) => n + l.text.length, 0).toLocaleString()} / 50,000 characters`,
  );

  function add() {
    if (lines.length >= MAX_LINES) {
      studio.say('render', 'A project can have 500 lines at most.', true);
      return;
    }
    const last = lines[lines.length - 1];
    const n = newLine(last ? last.voice : 'af_heart', last ? last.speaker : '');
    lines.push(n);
    void studio.focusLine(n.id);
  }
</script>

<section class="card" aria-labelledby="script-h">
  <div class="row" style="justify-content:space-between">
    <h2 id="script-h">Script</h2>
    <span class="hint" id="count">{count}</span>
  </div>
  <p class="hint">
    Inline tags: <code>[pause 1.5s]</code> (0.1–10 s) and <code>[break]</code> (paragraph pause). Other bracketed text is
    read aloud, and you'll get a warning. Keyboard: Alt+↑ / Alt+↓ moves the focused line.
  </p>
  <div id="lines">
    {#each lines as line, i (line.id)}
      <LineCard {studio} {line} index={i} />
    {/each}
  </div>
  <p class="hint" id="empty" hidden={lines.length > 0}>No lines yet. Add a line or paste a script above.</p>
  <button class="btn secondary" id="add" type="button" onclick={add}>+ Add line</button>
</section>
