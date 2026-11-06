<script lang="ts">
  import { tick } from 'svelte';
  import type { Studio } from '#lib/studio/studio.svelte.ts';

  let { studio }: { studio: Studio } = $props();

  const rows = $derived(studio.project.dictionary);
  let box: HTMLDivElement | undefined = $state();
  let addButton: HTMLButtonElement | undefined = $state();

  async function add() {
    rows.push(['', '']);
    await tick();
    box?.querySelector<HTMLInputElement>('.dictrow:last-child input')?.focus();
  }

  function remove(i: number) {
    rows.splice(i, 1);
    addButton?.focus();
  }
</script>

<section class="card" aria-labelledby="dict-h">
  <details>
    <summary id="dict-h"
      >Pronunciation dictionary <span class="hint" id="dict-count">{rows.length ? `(${rows.length})` : ''}</span
      ></summary
    >
    <p class="hint">
      Whole words, any case. Write a respelling (<code>Nginx → engine x</code>) or IPA phonemes between slashes (<code
        >GIF → /ɡɪf/</code
      >). Captions keep the original word.
    </p>
    <div id="dict" bind:this={box}>
      {#each rows as row, i (i)}
        <div class="dictrow">
          <input type="text" maxlength="60" placeholder="Word" aria-label={`Word ${i + 1}`} bind:value={row[0]} />
          <input
            type="text"
            maxlength="200"
            placeholder="Say it as… or /phonemes/"
            aria-label={`Pronunciation ${i + 1}`}
            bind:value={row[1]}
          />
          <button type="button" class="btn danger small" aria-label={`Remove word ${i + 1}`} onclick={() => remove(i)}
            >Remove</button
          >
        </div>
      {:else}
        <p class="hint">No words yet.</p>
      {/each}
    </div>
    <button class="btn secondary small" id="dict-add" type="button" bind:this={addButton} onclick={() => void add()}
      >+ Add word</button
    >
  </details>
</section>

<style>
  .dictrow {
    display: grid;
    grid-template-columns: 1fr 1fr auto;
    gap: 8px;
    margin-bottom: 6px;
  }
  .dictrow input {
    width: 100%;
    min-width: 0;
  }
</style>
