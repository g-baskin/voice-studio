<script lang="ts">
  import { onMount } from 'svelte';
  import { Editor } from '#lib/editor/editor.svelte.ts';
  import { PRODUCT } from '#lib/nav.ts';
  import ExportDialog from './ExportDialog.svelte';
  import Inspector from './Inspector.svelte';
  import MediaBin from './MediaBin.svelte';
  import MenuBar, { type Menu } from './MenuBar.svelte';
  import Preview from './Preview.svelte';
  import Timeline from './Timeline.svelte';

  const editor = new Editor();
  const mac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform);
  const mod = mac ? '⌘' : 'Ctrl+';

  let preview: Preview | undefined = $state();
  let timeline: Timeline | undefined = $state();
  let exporter: ExportDialog | undefined = $state();
  let help: HTMLDialogElement | undefined = $state();
  let importer: HTMLInputElement | undefined = $state();
  let renaming = $state(false);
  let nameDraft = $state('');

  const SAVE_TEXT = { saved: 'All changes saved', saving: 'Saving...', unsaved: 'Unsaved changes', error: 'Not saved' };
  const hasClips = $derived(editor.seq.clips.length > 0);
  const hasSelection = $derived(editor.selection.length > 0);
  const single = $derived(editor.selected.length === 1 ? editor.selected[0] : null);
  const singleMedia = $derived(single ? editor.mediaById.get(single.media) : undefined);

  onMount(() => {
    void editor.init();
    const leave = () => editor.flushOnExit();
    window.addEventListener('pagehide', leave);
    return () => {
      window.removeEventListener('pagehide', leave);
      editor.stop();
    };
  });

  function attempt(work: () => Promise<unknown>) {
    void work().catch((error: unknown) => editor.fail(error));
  }

  function rename() {
    nameDraft = editor.seq.name;
    renaming = true;
  }

  function finishRename(save: boolean) {
    renaming = false;
    const name = nameDraft.trim().slice(0, 80);
    if (save && name && name !== editor.seq.name) editor.commit((s) => (s.name = name));
  }

  function focusSelect(node: HTMLInputElement) {
    node.focus();
    node.select();
  }

  function selectAll() {
    editor.selection = editor.seq.clips.map((c) => c.id);
  }

  const menus: Menu[] = $derived([
    {
      label: 'File',
      items: [
        { label: 'New sequence', run: () => attempt(() => editor.create()) },
        { label: 'Import media...', shortcut: `${mod}I`, run: () => importer?.click() },
        'separator',
        { label: 'Rename sequence...', run: rename },
        { label: 'Delete sequence...', disabled: !editor.seqId, run: () => deleteSequence() },
        'separator',
        { label: 'Save', shortcut: `${mod}S`, run: () => attempt(() => editor.save()) },
        { label: 'Export...', shortcut: `${mod}E`, disabled: !hasClips, run: () => exporter?.open() },
      ],
    },
    {
      label: 'Edit',
      items: [
        { label: 'Undo', shortcut: `${mod}Z`, disabled: !editor.undoCount, run: () => editor.undo() },
        { label: 'Redo', shortcut: mac ? '⇧⌘Z' : 'Ctrl+Y', disabled: !editor.redoCount, run: () => editor.redo() },
        'separator',
        { label: 'Select all', shortcut: `${mod}A`, disabled: !hasClips, run: selectAll },
        { label: 'Deselect', shortcut: 'Esc', disabled: !hasSelection, run: () => (editor.selection = []) },
        'separator',
        { label: 'Delete', shortcut: 'Delete', disabled: !hasSelection, run: () => editor.deleteSelected(false) },
        {
          label: 'Ripple delete',
          shortcut: '⇧Delete',
          disabled: !hasSelection,
          run: () => editor.deleteSelected(true),
        },
      ],
    },
    {
      label: 'Clip',
      items: [
        {
          label: 'Split at playhead',
          shortcut: `${mod}K`,
          disabled: !hasClips,
          run: () => editor.splitAt(editor.playhead),
        },
        {
          label: 'Add cross dissolve',
          shortcut: `${mod}D`,
          disabled: !single,
          run: () => editor.addDissolve(),
        },
        {
          label: 'Detach audio',
          disabled: !single || singleMedia?.kind !== 'video' || !singleMedia.has_audio,
          run: () => single && editor.detachAudio(single),
        },
        'separator',
        {
          label: 'Mute clip',
          disabled: !single,
          checked: single?.muted ?? false,
          run: () =>
            editor.commit((s) => {
              const c = s.clips.find((x) => x.id === single?.id);
              if (c) c.muted = !c.muted;
            }),
        },
      ],
    },
    {
      label: 'Sequence',
      items: [
        { label: 'Mark in', shortcut: 'I', run: () => editor.setIn(editor.playhead) },
        { label: 'Mark out', shortcut: 'O', run: () => editor.setOut(editor.playhead) },
        {
          label: 'Clear in and out',
          shortcut: '⌥X',
          disabled: editor.seq.range_in === null && editor.seq.range_out === null,
          run: () => editor.clearInOut(),
        },
        { label: 'Add marker', shortcut: 'M', run: () => editor.addMarker(editor.playhead) },
        'separator',
        { label: 'Add video track', run: () => editor.addTrack('video') },
        { label: 'Add audio track', run: () => editor.addTrack('audio') },
        'separator',
        { label: 'Sequence settings', run: () => ((editor.selection = []), (editor.selectedTrack = null)) },
      ],
    },
    {
      label: 'View',
      items: [
        { label: 'Zoom in', shortcut: '=', run: () => timeline?.setZoom(editor.zoom * 1.5) },
        { label: 'Zoom out', shortcut: '-', run: () => timeline?.setZoom(editor.zoom / 1.5) },
        { label: 'Zoom to fit', shortcut: '\\', run: () => timeline?.zoomToFit() },
        'separator',
        { label: 'Snapping', shortcut: 'S', checked: editor.snapping, run: () => (editor.snapping = !editor.snapping) },
        {
          label: 'Selection tool',
          shortcut: 'V',
          checked: editor.tool === 'select',
          run: () => (editor.tool = 'select'),
        },
        { label: 'Razor tool', shortcut: 'C', checked: editor.tool === 'razor', run: () => (editor.tool = 'razor') },
      ],
    },
    {
      label: 'Help',
      items: [{ label: 'Keyboard shortcuts', shortcut: '?', run: () => help?.showModal() }],
    },
  ]);

  function deleteSequence() {
    if (confirm(`Delete the sequence "${editor.seq.name}"? Media stays in the bin.`)) attempt(() => editor.remove());
  }

  function typing(target: EventTarget | null): boolean {
    if (!(target instanceof HTMLElement)) return false;
    if (target.isContentEditable || target.closest('dialog[open], [role="menu"]')) return true;
    if (target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement) return true;
    return target instanceof HTMLInputElement && !['checkbox', 'radio', 'button', 'range'].includes(target.type);
  }

  function keys(e: KeyboardEvent) {
    if (e.defaultPrevented || typing(e.target)) return;
    const cmd = mac ? e.metaKey : e.ctrlKey;
    const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;
    const on = (run: () => void) => {
      e.preventDefault();
      run();
    };
    if (cmd) {
      if (key === 'z' && !e.shiftKey) on(() => editor.undo());
      else if ((key === 'z' && e.shiftKey) || key === 'y') on(() => editor.redo());
      else if (key === 'k') on(() => editor.splitAt(editor.playhead));
      else if (key === 'd') on(() => editor.addDissolve());
      else if (key === 'a') on(selectAll);
      else if (key === 's') on(() => attempt(() => editor.save()));
      else if (key === 'e') on(() => hasClips && exporter?.open());
      else if (key === 'i') on(() => importer?.click());
      return;
    }
    if (e.altKey) {
      if (e.code === 'KeyX') on(() => editor.clearInOut());
      return;
    }
    // A focused button keeps Space and Enter for itself.
    const onButton =
      e.target instanceof HTMLButtonElement ||
      (e.target instanceof HTMLElement && e.target.closest('[role="menubar"]'));
    switch (key) {
      case ' ':
        if (!onButton) on(() => preview?.toggle());
        break;
      case 'k':
        on(() => preview?.pause());
        break;
      case 'l':
        on(() => preview?.play());
        break;
      case 'j':
        on(() => preview?.step(-1));
        break;
      case 'ArrowLeft':
        on(() => preview?.step((e.shiftKey ? -10 : -1) / editor.seq.fps));
        break;
      case 'ArrowRight':
        on(() => preview?.step((e.shiftKey ? 10 : 1) / editor.seq.fps));
        break;
      case 'ArrowUp':
        on(() => preview?.jumpEdit(-1));
        break;
      case 'ArrowDown':
        on(() => preview?.jumpEdit(1));
        break;
      case 'Home':
        on(() => preview?.home(false));
        break;
      case 'End':
        on(() => preview?.home(true));
        break;
      case 'i':
        on(() => editor.setIn(editor.playhead));
        break;
      case 'o':
        on(() => editor.setOut(editor.playhead));
        break;
      case 'm':
        on(() => editor.addMarker(editor.playhead));
        break;
      case 'v':
        on(() => (editor.tool = 'select'));
        break;
      case 'c':
        on(() => (editor.tool = 'razor'));
        break;
      case 's':
        on(() => (editor.snapping = !editor.snapping));
        break;
      case '=':
      case '+':
        on(() => timeline?.setZoom(editor.zoom * 1.5));
        break;
      case '-':
        on(() => timeline?.setZoom(editor.zoom / 1.5));
        break;
      case '\\':
        on(() => timeline?.zoomToFit());
        break;
      case 'Delete':
      case 'Backspace':
        if (hasSelection) on(() => editor.deleteSelected(e.shiftKey));
        break;
      case 'Escape':
        on(() => (editor.selection = []));
        break;
      case '?':
        on(() => help?.showModal());
        break;
    }
  }

  const SHORTCUTS = [
    ['Space / L / K', 'Play, play, pause'],
    ['J', 'Back one second'],
    ['← →', 'Step one frame (Shift: ten frames)'],
    ['↑ ↓', 'Previous or next edit point'],
    ['Home / End', 'Start or end of the sequence'],
    ['I / O', 'Mark in and out points'],
    ['⌥X', 'Clear in and out'],
    ['M', 'Add a marker'],
    ['V / C', 'Selection tool or razor tool'],
    ['S', 'Snapping on or off'],
    [`${mod}K`, 'Split at the playhead (selected clips, or every track)'],
    [`${mod}D`, 'Cross dissolve into the selected clip'],
    ['Delete / ⇧Delete', 'Delete, or ripple delete (close the gap)'],
    ['Alt-drag', 'Move without snapping'],
    [`${mod}Z / ${mac ? '⇧⌘Z' : 'Ctrl+Y'}`, 'Undo or redo'],
    ['= / - / \\', 'Zoom in, zoom out, zoom to fit'],
  ];
</script>

<svelte:head><title>Editor · {PRODUCT}</title></svelte:head>
<svelte:window onkeydown={keys} />

<input
  bind:this={importer}
  type="file"
  multiple
  hidden
  accept=".mp4,.mov,.m4v,.webm,.mkv,.avi,.wav,.mp3,.m4a,.aac,.flac,.ogg,.opus,.aif,.aiff,.png,.jpg,.jpeg,.webp"
  onchange={() => {
    if (importer?.files?.length) void editor.upload([...importer.files]);
    if (importer) importer.value = '';
  }}
/>

<div class="editor">
  <h1 class="visually-hidden">Editor</h1>
  <div class="bar">
    <MenuBar {menus} />
    <div class="name">
      {#if renaming}
        <input
          aria-label="Sequence name"
          maxlength="80"
          bind:value={nameDraft}
          {@attach focusSelect}
          onblur={() => finishRename(true)}
          onkeydown={(e) => {
            if (e.key === 'Enter') finishRename(true);
            else if (e.key === 'Escape') finishRename(false);
          }}
        />
      {:else}
        <select
          aria-label="Open sequence"
          value={editor.seqId ?? ''}
          onchange={(e) => attempt(() => editor.open((e.currentTarget as HTMLSelectElement).value))}
        >
          {#if !editor.seqId}<option value="">{editor.seq.name}</option>{/if}
          {#each editor.sequences as s (s.id)}<option value={s.id}
              >{s.id === editor.seqId ? editor.seq.name : s.name}</option
            >{/each}
        </select>
        <button type="button" class="ghost" onclick={rename} aria-label="Rename sequence" title="Rename">✎</button>
      {/if}
      <span class="save {editor.saveState}" role="status">{SAVE_TEXT[editor.saveState]}</span>
    </div>
    <div class="tools">
      <button
        type="button"
        class="ghost"
        disabled={!editor.undoCount}
        onclick={() => editor.undo()}
        aria-label="Undo"
        title="Undo ({mod}Z)">↶</button
      >
      <button
        type="button"
        class="ghost"
        disabled={!editor.redoCount}
        onclick={() => editor.redo()}
        aria-label="Redo"
        title="Redo">↷</button
      >
      <button type="button" class="btn exp" disabled={!hasClips} onclick={() => exporter?.open()}>Export</button>
    </div>
  </div>

  <div class="panels">
    <MediaBin {editor} />
    <Preview bind:this={preview} {editor} />
    <Inspector {editor} />
  </div>
  <Timeline bind:this={timeline} {editor} />
  <p class="message" class:bad={editor.messageBad} role="status" aria-live="polite">{editor.message}</p>
</div>

<ExportDialog bind:this={exporter} {editor} />

<dialog bind:this={help} class="help" aria-labelledby="help-title">
  <form method="dialog">
    <h2 id="help-title">Keyboard shortcuts</h2>
    <dl>
      {#each SHORTCUTS as [k, what] (k)}<dt><kbd>{k}</kbd></dt>
        <dd>{what}</dd>{/each}
    </dl>
    <p class="hint">
      Drag media from the bin onto a track. Drag clip edges to trim; drop on another clip to overwrite.
    </p>
    <button class="btn">Close</button>
  </form>
</dialog>

<style>
  /* The editor fills the window below the app header, like a desktop editor. */
  :global(main.page:has(> .editor)) {
    max-width: none;
    padding: 0;
    margin: 0;
  }
  .editor {
    display: grid;
    /* minmax(0) keeps the wide timeline scrolling inside its panel instead of widening the page. */
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: auto minmax(220px, 1fr) minmax(220px, 42vh) auto;
    height: calc(100dvh - 57px);
    min-height: 620px;
  }
  .bar {
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 4px 10px;
    border-bottom: 1px solid var(--line);
    background: var(--card);
  }
  .name {
    display: flex;
    align-items: center;
    gap: 6px;
    flex: 1;
    min-width: 0;
    justify-content: center;
  }
  .name select,
  .name input {
    font: inherit;
    font-size: 0.88rem;
    font-weight: 600;
    max-width: 260px;
    padding: 3px 8px;
  }
  .save {
    font-size: 0.78rem;
    color: var(--muted);
    white-space: nowrap;
  }
  .save.error {
    color: var(--bad);
  }
  .tools {
    display: flex;
    align-items: center;
    gap: 4px;
  }
  .ghost {
    font: inherit;
    width: 30px;
    height: 28px;
    padding: 0;
    color: var(--ink);
    background: none;
    border: 1px solid transparent;
    border-radius: 6px;
    cursor: pointer;
  }
  .ghost:hover:not(:disabled) {
    background: var(--bg);
    border-color: var(--line);
  }
  .ghost:disabled {
    opacity: 0.4;
  }
  .exp {
    padding: 5px 16px;
    font-size: 0.88rem;
  }
  .panels {
    display: grid;
    grid-template-columns: minmax(200px, 250px) minmax(0, 1fr) minmax(230px, 280px);
    min-height: 0;
    border-bottom: 1px solid var(--line);
  }
  .message {
    margin: 0;
    padding: 3px 12px;
    min-height: 1.6em;
    font-size: 0.8rem;
    color: var(--muted);
    background: var(--card);
    border-top: 1px solid var(--line);
  }
  .message.bad {
    color: var(--bad);
  }
  .help {
    border: 1px solid var(--line);
    border-radius: var(--radius);
    background: var(--card);
    color: var(--ink);
    width: min(520px, calc(100vw - 32px));
  }
  .help::backdrop {
    background: rgb(0 0 0 / 0.45);
  }
  .help h2 {
    margin-top: 0;
  }
  dl {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 6px 14px;
    margin: 0 0 12px;
  }
  dt {
    text-align: right;
  }
  dd {
    margin: 0;
  }
  kbd {
    font: inherit;
    font-size: 0.82rem;
    padding: 1px 6px;
    border: 1px solid var(--line);
    border-radius: 4px;
    background: var(--bg);
  }
  .visually-hidden {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
  }
  @media (max-width: 900px) {
    .panels {
      grid-template-columns: minmax(0, 1fr);
      grid-template-rows: 200px minmax(240px, 1fr) auto;
    }
    .editor {
      height: auto;
      grid-template-rows: auto auto minmax(260px, auto) auto;
    }
  }
</style>
