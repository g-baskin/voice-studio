<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { PRODUCT } from '#lib/nav.ts';
  import { errorText, getJson } from '#lib/studio/api.ts';
  import { DEFAULT_TEXT, DRAFT, FALLBACK_VOICE, newLine } from '#lib/studio/logic.ts';
  import { Studio } from '#lib/studio/studio.svelte.ts';
  import type { Draft, GenStatus, RewriteStatus, Style, Voice } from '#lib/studio/types.ts';
  import DictionaryCard from './DictionaryCard.svelte';
  import ExportCard from './ExportCard.svelte';
  import PasteCard from './PasteCard.svelte';
  import ProjectCard from './ProjectCard.svelte';
  import RenderCard from './RenderCard.svelte';
  import ScriptCard from './ScriptCard.svelte';
  import ScriptWriter from './ScriptWriter.svelte';

  const studio = new Studio();
  let booted = $state(false);
  let genStatus = $state<GenStatus | null>(null);
  let genLoaded = $state(false);
  let projectCard: ProjectCard | undefined = $state();
  let renderCard: RenderCard | undefined = $state();
  let draftTimer: ReturnType<typeof setTimeout> | undefined;

  // Never overwrite a stored draft with the empty state before boot has restored it.
  $effect(() => {
    if (!booted) return;
    const snapshot = JSON.stringify({ projectId: studio.projectId, project: studio.payload() });
    clearTimeout(draftTimer);
    draftTimer = setTimeout(() => {
      try {
        localStorage.setItem(DRAFT, snapshot);
      } catch {
        // Storage full or blocked.
      }
    }, 400);
  });

  onDestroy(() => clearTimeout(draftTimer));

  function onPageHide() {
    if (!booted) return;
    clearTimeout(draftTimer);
    studio.saveDraft();
  }

  function onKey(e: KeyboardEvent) {
    if (!(e.metaKey || e.ctrlKey)) return;
    if (e.key.toLowerCase() === 's' && !e.shiftKey) {
      e.preventDefault();
      void projectCard?.save();
    } else if (e.key === 'Enter' && e.shiftKey) {
      e.preventDefault();
      void renderCard?.render();
    }
  }

  function readDraft(): Draft | null {
    try {
      const d: unknown = JSON.parse(localStorage.getItem(DRAFT) || 'null');
      if (d && typeof d === 'object' && 'project' in d) {
        const draft = d as Draft;
        if (draft.project && Array.isArray(draft.project.lines)) return draft;
      }
    } catch {
      // Corrupt draft.
    }
    return null;
  }

  function handOffVoice() {
    const want = new URLSearchParams(location.search).get('voice');
    if (!want || !/^[a-z0-9_:]{3,40}$/.test(want)) return;
    const v = studio.catalog.find((x) => x.id === want);
    if (!v) return;
    const lines = studio.project.lines;
    let target = lines.find((l) => !l.text.trim());
    if (!target) {
      lines.push(newLine(want));
      target = lines[lines.length - 1];
    }
    target.voice = want;
    void studio.focusLine(target.id);
    studio.say('proj', `Voice “${v.name}” from the Voice Lab is on line ${lines.indexOf(target) + 1}.`);
    history.replaceState(null, '', location.pathname);
  }

  onMount(async () => {
    try {
      const p = await getJson<{ delivery: Record<string, { does: string }> }>('/presets');
      for (const [k, v] of Object.entries(p.delivery)) studio.deliveryInfo[k] = v.does;
    } catch {
      // Labels fall back to names.
    }
    const [styles, clone, rewrite] = await Promise.allSettled([
      getJson<{ styles?: Style[] }>('/styles'),
      fetch('/api/clone/status').then((r) =>
        r.ok ? (r.json() as Promise<{ emotion_tags?: unknown }>) : { emotion_tags: [] },
      ),
      fetch('/api/rewrite/status').then((r) => (r.ok ? (r.json() as Promise<RewriteStatus>) : null)),
    ]);
    if (styles.status === 'fulfilled') studio.myStyles = styles.value.styles ?? [];
    if (clone.status === 'fulfilled' && Array.isArray(clone.value.emotion_tags))
      studio.cloneTags = clone.value.emotion_tags
        .map((t) => String(t).replace(/^\[|\]$/g, ''))
        .filter((t) => /^[a-z][a-z _-]{0,30}$/i.test(t));
    if (rewrite.status === 'fulfilled') studio.rewriteStatus = rewrite.value;
    try {
      const r = await fetch('/api/voices');
      const body = (await r.json()) as { catalog?: Voice[]; detail?: string };
      if (!r.ok || !body.catalog) throw new Error(body.detail || 'Voices unavailable.');
      studio.catalog = body.catalog;
    } catch (e) {
      studio.say('render', 'Voice list unavailable: ' + errorText(e), true);
      studio.catalog = [FALLBACK_VOICE];
    }
    const draft = readDraft();
    if (draft) {
      studio.projectId = /^[0-9a-f]{12}$/.test(draft.projectId || '') ? draft.projectId : null;
      studio.load(draft.project);
      studio.say('proj', 'Restored your unsaved draft from this browser.');
    } else {
      studio.load({ title: 'Untitled project', lines: [newLine('af_heart', 'Narrator', DEFAULT_TEXT)] });
    }
    handOffVoice();
    try {
      const r = await fetch('/api/scriptgen/status');
      genStatus = r.ok ? ((await r.json()) as GenStatus) : null;
    } catch {
      genStatus = null;
    }
    genLoaded = true;
    booted = true;
  });
</script>

<svelte:head><title>Studio · {PRODUCT}</title></svelte:head>
<svelte:window onpagehide={onPageHide} />
<svelte:document onkeydown={onKey} />

<h1>Studio</h1>
<p class="lede">
  Write a script, give each line a voice and a delivery, then render a mastered mix with captions. Everything runs on
  this computer.
</p>

<ProjectCard {studio} ready={booted} bind:this={projectCard} />
<PasteCard {studio} />
<ScriptWriter {studio} status={genStatus} loaded={genLoaded} />
<ScriptCard {studio} />
<DictionaryCard {studio} />
<ExportCard {studio} />
<RenderCard {studio} ready={booted} bind:this={renderCard} />

<style>
  :global(.grid) {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 12px;
  }
  :global(.field) {
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-width: 0;
  }
  :global(.field input),
  :global(.field select),
  :global(.field textarea) {
    width: 100%;
  }
  :global(.row) {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
  }
  :global(.small) {
    padding: 6px 10px;
    font-size: 0.9rem;
    font-weight: 500;
  }
  :global(audio) {
    width: 100%;
    margin: 8px 0;
  }
  :global(ul.plain) {
    list-style: none;
    padding: 0;
    margin: 8px 0 0;
  }
  :global(ul.plain li) {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
    justify-content: space-between;
    padding: 6px 0;
    border-bottom: 1px solid var(--line);
  }
  :global(.meter) {
    font-variant-numeric: tabular-nums;
  }
  :global(.ok) {
    color: var(--good);
  }
  :global(.bad) {
    color: var(--bad);
  }
  :global(h2) {
    font-size: 1.15rem;
    margin: 0 0 10px;
  }
  :global(details > summary) {
    cursor: pointer;
    font-weight: 600;
  }
  :global(.sticky) {
    position: sticky;
    bottom: 0;
    background: var(--card);
    border-top: 1px solid var(--line);
    padding: 12px 16px;
    z-index: 2;
  }
  :global(.btn[aria-pressed='true']) {
    background: var(--accent);
    color: var(--accent-ink);
  }
  :global(.wrapword) {
    overflow-wrap: anywhere;
  }
  @media (max-width: 560px) {
    :global(.grid) {
      grid-template-columns: 1fr;
    }
    :global(.card) {
      padding: 16px;
    }
  }
</style>
