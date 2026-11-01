<script lang="ts">
  import { onMount, tick, untrack } from 'svelte';
  import { detailText, errorText } from '#lib/studio/api.ts';
  import { diffView, tagsOf, type DiffPart } from '#lib/studio/logic.ts';
  import type { RewriteResult, RewriteStatus } from '#lib/studio/types.ts';

  let {
    text,
    status,
    onaccept,
    onclose,
  }: {
    text: string;
    status: RewriteStatus | null;
    onaccept: (text: string) => void;
    onclose: () => void;
  } = $props();

  type Outcome =
    | { kind: 'idle' }
    | { kind: 'busy' }
    | { kind: 'error'; message: string }
    | { kind: 'same' }
    | { kind: 'diff'; result: RewriteResult; parts: DiffPart[] };

  // The text is fixed when the panel opens, like the legacy panel.
  const original = untrack(() => text);
  const llmOk = untrack(() => !!status?.llm?.available);
  const tones = untrack(() => status?.tones ?? ['natural']);
  let useLlm = $state(false);
  let conversational = $state(false);
  let tone = $state(tones[0] ?? 'natural');
  let outcome = $state<Outcome>({ kind: 'idle' });
  let go: HTMLButtonElement | undefined = $state();
  let accept: HTMLButtonElement | undefined = $state();

  onMount(() => go?.focus());

  async function call(t: string): Promise<RewriteResult> {
    const r = await fetch('/api/rewrite', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: t, mode: useLlm ? 'llm' : 'rules', tone, conversational }),
    });
    if (!r.ok) throw new Error((await detailText(r)) || `Rewrite failed (${r.status}).`);
    return (await r.json()) as RewriteResult;
  }

  async function run() {
    outcome = { kind: 'busy' };
    try {
      let r = await call(original);
      if (tagsOf(r.text).join('|') !== tagsOf(original).join('|')) {
        // The rewrite changed a [tag]: rewrite only the text between tags and keep every tag exactly.
        const parts = original.split(/(\[[^\]\n[]{1,40}\])/);
        const done = await Promise.all(
          parts.map((p, k) =>
            k % 2 || !p.trim()
              ? Promise.resolve<RewriteResult>({ text: p, notes: [] })
              : call(p).then((x) => ({
                  ...x,
                  text: (p.match(/^\s*/)?.[0] ?? '') + x.text.trim() + (p.match(/\s*$/)?.[0] ?? ''),
                })),
          ),
        );
        r = {
          text: done.map((x) => x.text).join(''),
          engine: r.engine,
          notes: [...new Set(done.flatMap((x) => x.notes ?? []))].concat(['Kept your [tags] exactly as written.']),
        };
      }
      if (r.text === original) {
        outcome = { kind: 'same' };
        return;
      }
      outcome = { kind: 'diff', result: r, parts: diffView(original, r.text) };
      await tick();
      accept?.focus();
    } catch (e) {
      outcome = { kind: 'error', message: errorText(e) };
    }
  }
</script>

{#if !original.trim()}
  <p class="error">Nothing to rewrite yet.</p>
{:else}
  <div class="rewrite">
    <div class="row">
      <label><input type="checkbox" bind:checked={conversational} /> Make it conversational</label>
      <label><input type="checkbox" bind:checked={useLlm} disabled={!llmOk} /> Use a language model</label>
      <select aria-label="Rewrite tone" bind:value={tone} disabled={!useLlm}>
        {#each tones as t (t)}<option value={t}>{t}</option>{/each}
      </select>
      <button
        type="button"
        class="btn small"
        bind:this={go}
        disabled={outcome.kind === 'busy'}
        onclick={() => void run()}>Show rewrite</button
      >
      <button type="button" class="btn secondary small" onclick={onclose}>Cancel</button>
    </div>
    {#if llmOk}
      <p class="hint">Language model via {status?.llm?.via}. [tags] are kept.</p>
    {:else}
      <p class="hint">
        Built-in rules only. For a language-model rewrite, connect an AI in “Write a script for me” → Connect AI. [tags]
        are kept.
      </p>
    {/if}
    <div role="status" aria-live="polite">
      {#if outcome.kind === 'busy'}
        <p class="hint">Rewriting…</p>
      {:else if outcome.kind === 'error'}
        <p class="error">{outcome.message}</p>
      {:else if outcome.kind === 'same'}
        <p class="hint">No changes suggested: this already reads well aloud.</p>
      {:else if outcome.kind === 'diff'}
        {@const r = outcome.result}
        <p class="hint">Before → after ({r.engine || 'rules'}): red is removed, green is added.</p>
        <!-- prettier-ignore -->
        <p class="diff wrapword">{#each outcome.parts as part, k (k)}{#if part.kind === 'del'}<del>{part.text}</del>{:else if part.kind === 'ins'}<ins>{part.text}</ins>{:else}{part.text}{/if}{/each}</p>
        {#if r.notes?.length}
          <ul class="hint">
            {#each r.notes as n, k (k)}<li>{n}</li>{/each}
          </ul>
        {/if}
        <div class="row">
          <button type="button" class="btn small" bind:this={accept} onclick={() => onaccept(r.text)}
            >Accept rewrite</button
          >
          <button type="button" class="btn secondary small" onclick={onclose}>Keep original</button>
        </div>
      {/if}
    </div>
  </div>
{/if}

<style>
  .rewrite {
    border: 1px dashed var(--line);
    border-radius: 8px;
    padding: 10px;
    margin-top: 8px;
  }
  .diff {
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 10px;
    white-space: pre-wrap;
  }
  .diff del {
    margin-right: 0.3em;
    padding: 0 2px;
    border-radius: 3px;
    color: var(--bad);
    background: color-mix(in srgb, var(--bad) 12%, transparent);
  }
  .diff ins {
    padding: 0 2px;
    border-radius: 3px;
    color: var(--good);
    background: color-mix(in srgb, var(--good) 14%, transparent);
    text-decoration: none;
    font-weight: 600;
  }
</style>
