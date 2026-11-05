<script lang="ts">
  import { onMount } from 'svelte';
  import { replaceState } from '$app/navigation';
  import { Editor } from '#lib/editor/editor.svelte.ts';
  import { PRODUCT } from '#lib/nav.ts';
  import ExportDialog from './ExportDialog.svelte';
  import ClipPanel from './ClipPanel.svelte';
  import Inspector from './Inspector.svelte';
  import MediaBin from './MediaBin.svelte';
  import MenuBar, { type Menu } from './MenuBar.svelte';
  import Preview from './Preview.svelte';
  import SourceMonitor from './SourceMonitor.svelte';
  import Timeline from './Timeline.svelte';

  const editor = new Editor();
  const mac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform);
  const mod = mac ? '⌘' : 'Ctrl+';

  let preview: Preview | undefined = $state();
  let source: SourceMonitor | undefined = $state();
  let timeline: Timeline | undefined = $state();
  let exporter: ExportDialog | undefined = $state();
  let help: HTMLDialogElement | undefined = $state();
  let importer: HTMLInputElement | undefined = $state();
  let renaming = $state(false);
  let nameDraft = $state('');
  let panelsEl: HTMLDivElement | undefined = $state();
  // Timeline height in pixels; null keeps the default share of the window.
  let timelineH: number | null = $state(null);
  let sizing: { y0: number; h0: number; max: number } | null = null;
  let shownH = $state(0);

  const TIMELINE_KEY = 'sharkaudio.editor.timelineHeight';
  const MIN_TIMELINE = 160;
  const MIN_PANELS = 160;

  const SAVE_TEXT = { saved: 'All changes saved', saving: 'Saving...', unsaved: 'Unsaved changes', error: 'Not saved' };
  const hasClips = $derived(editor.seq.clips.length > 0);
  const hasSelection = $derived(editor.selection.length > 0);
  const single = $derived(editor.selected.length === 1 ? editor.selected[0] : null);
  const singleMedia = $derived(single ? editor.mediaById.get(single.media) : undefined);
  const clipMode = $derived(editor.mode === 'clip');
  const hasSource = $derived(editor.source !== null);
  const hasRange = $derived(editor.seq.range_in !== null && editor.seq.range_out !== null);
  // The viewer that I, O, M and the transport keys drive.
  const onSource = $derived(clipMode && editor.viewer === 'source' && hasSource);

  onMount(() => {
    const saved = Number(localStorage.getItem(TIMELINE_KEY));
    if (Number.isFinite(saved) && saved >= MIN_TIMELINE) timelineH = Math.round(saved);
    const asked = new URLSearchParams(location.search).get('mode');
    editor.setMode(asked === 'clip' || asked === 'edit' ? asked : editor.savedMode());
    void editor.init();
    const tl = timelineEl();
    const watch = new ResizeObserver(() => (shownH = Math.round(tl?.getBoundingClientRect().height ?? 0)));
    if (tl) watch.observe(tl);
    const leave = () => editor.flushOnExit();
    window.addEventListener('pagehide', leave);
    return () => {
      window.removeEventListener('pagehide', leave);
      watch.disconnect();
      editor.stop();
    };
  });

  function timelineEl(): HTMLElement | null {
    return document.querySelector('.editor > .timeline');
  }

  function setTimelineHeight(h: number | null, max = Infinity) {
    timelineH = h === null ? null : Math.round(Math.max(MIN_TIMELINE, Math.min(h, max)));
    if (timelineH === null) localStorage.removeItem(TIMELINE_KEY);
    else localStorage.setItem(TIMELINE_KEY, String(timelineH));
  }

  // Room the timeline may take: everything above the panels' minimum height.
  function maxTimeline(h0: number) {
    return h0 + Math.max(0, (panelsEl?.getBoundingClientRect().height ?? 0) - MIN_PANELS);
  }

  function startSplit(e: PointerEvent) {
    if (e.button !== 0) return;
    const h0 = timelineEl()?.getBoundingClientRect().height ?? 0;
    e.preventDefault();
    sizing = { y0: e.clientY, h0, max: maxTimeline(h0) };
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  }

  function moveSplit(e: PointerEvent) {
    if (sizing) setTimelineHeight(sizing.h0 - (e.clientY - sizing.y0), sizing.max);
  }

  function splitKey(e: KeyboardEvent) {
    const h0 = timelineEl()?.getBoundingClientRect().height ?? 0;
    const step = e.shiftKey ? 80 : 20;
    const next =
      e.key === 'ArrowUp'
        ? h0 + step
        : e.key === 'ArrowDown'
          ? h0 - step
          : e.key === 'Home'
            ? MIN_TIMELINE
            : e.key === 'End'
              ? Infinity
              : null;
    if (e.key === 'Enter') {
      e.preventDefault();
      setTimelineHeight(null);
      return;
    }
    if (next === null) return;
    e.preventDefault();
    setTimelineHeight(next, maxTimeline(h0));
  }

  function setMode(mode: 'edit' | 'clip') {
    editor.setMode(mode);
    const url = new URL(location.href);
    if (mode === 'clip') url.searchParams.set('mode', 'clip');
    else url.searchParams.delete('mode');
    replaceState(url, {});
  }

  function slipToFirstFrame() {
    editor.commit((s) => {
      const c = s.clips.find((x) => x.id === single?.id);
      if (!c) return;
      c.source_out -= c.source_in;
      c.source_in = 0;
    });
    editor.say('Clip now starts at the first frame of its source.');
  }

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
        {
          label: 'Slip to first frame',
          disabled: !single || singleMedia?.kind === 'image' || single.source_in <= 0,
          run: slipToFirstFrame,
        },
        'separator',
        { label: 'Insert from source', shortcut: ',', disabled: !hasSource, run: () => editor.sourceEdit('insert') },
        {
          label: 'Overwrite from source',
          shortcut: '.',
          disabled: !hasSource,
          run: () => editor.sourceEdit('overwrite'),
        },
        {
          label: 'Smart insert at nearest edit',
          shortcut: '⇧,',
          disabled: !hasSource,
          run: () => editor.sourceEdit('smart'),
        },
        { label: 'Append to end', shortcut: '⇧.', disabled: !hasSource, run: () => editor.sourceEdit('append') },
        { label: 'Make subclip', shortcut: `${mod}U`, disabled: !hasSource, run: () => editor.makeSubclip() },
        'separator',
        {
          label: 'Ripple trim previous edit to playhead',
          shortcut: 'Q',
          disabled: !hasClips,
          run: () => editor.trimEditToPlayhead('previous', true),
        },
        {
          label: 'Ripple trim next edit to playhead',
          shortcut: 'W',
          disabled: !hasClips,
          run: () => editor.trimEditToPlayhead('next', true),
        },
        {
          label: 'Trim previous edit to playhead',
          shortcut: '⌥Q',
          disabled: !hasClips,
          run: () => editor.trimEditToPlayhead('previous', false),
        },
        {
          label: 'Trim next edit to playhead',
          shortcut: '⌥W',
          disabled: !hasClips,
          run: () => editor.trimEditToPlayhead('next', false),
        },
        { label: 'Extend edit to playhead', shortcut: 'E', disabled: !single, run: () => editor.extendToPlayhead() },
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
        { label: 'Mark clip', shortcut: 'X', disabled: !hasClips, run: () => editor.markClip() },
        { label: 'Add marker', shortcut: 'M', run: () => editor.addMarker(editor.playhead) },
        'separator',
        { label: 'Lift', shortcut: ';', disabled: !hasRange, run: () => editor.liftOrExtract(false) },
        { label: 'Extract', shortcut: "'", disabled: !hasRange, run: () => editor.liftOrExtract(true) },
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
        { label: 'Edit mode', checked: !clipMode, run: () => setMode('edit') },
        { label: 'Clip mode', checked: clipMode, run: () => setMode('clip') },
        'separator',
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
        { label: 'Slip tool', shortcut: 'Y', checked: editor.tool === 'slip', run: () => (editor.tool = 'slip') },
        {
          label: 'Ripple tool',
          shortcut: 'B',
          checked: editor.tool === 'ripple',
          run: () => (editor.tool = 'ripple'),
        },
        { label: 'Roll tool', shortcut: 'N', checked: editor.tool === 'roll', run: () => (editor.tool = 'roll') },
        { label: 'Slide tool', shortcut: 'U', checked: editor.tool === 'slide', run: () => (editor.tool = 'slide') },
        'separator',
        { label: 'Taller tracks', run: () => editor.resizeTracks(1.25) },
        { label: 'Shorter tracks', run: () => editor.resizeTracks(0.8) },
        { label: 'Reset track heights', run: () => editor.resizeTracks(0) },
        { label: 'Reset timeline size', disabled: timelineH === null, run: () => setTimelineHeight(null) },
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

  let holdingK = false;

  function keysUp(e: KeyboardEvent) {
    // Option changes e.key on a Mac, so the physical key is checked too.
    if (e.code === 'KeyK' || e.key.toLowerCase() === 'k') holdingK = false;
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
      else if (key === 'u') on(() => editor.makeSubclip());
      return;
    }
    // Option changes the character on a Mac keyboard, so these match the physical key.
    if (e.altKey) {
      if (e.code === 'KeyX') on(() => (onSource ? editor.clearSourceMarks() : editor.clearInOut()));
      else if (e.code === 'KeyQ') on(() => editor.trimEditToPlayhead('previous', false));
      else if (e.code === 'KeyW') on(() => editor.trimEditToPlayhead('next', false));
      return;
    }
    const player = onSource ? source : preview;
    // A focused button keeps Space and Enter for itself.
    const onButton =
      e.target instanceof HTMLButtonElement ||
      (e.target instanceof HTMLElement && e.target.closest('[role="menubar"]'));
    switch (key) {
      case ' ':
        if (!onButton) on(() => player?.toggle());
        break;
      case 'k':
        holdingK = true;
        on(() => player?.shuttle('k'));
        break;
      case 'j':
      case 'l':
        // Holding K turns J and L into single-frame steps, as in other editors. Key repeat would race the
        // shuttle to 8×, so only real presses change speed.
        if (e.repeat && !holdingK) e.preventDefault();
        else if (holdingK) on(() => player?.step((key === 'j' ? -1 : 1) / editor.seq.fps));
        else on(() => player?.shuttle(key));
        break;
      case 'ArrowLeft':
        on(() => player?.step((e.shiftKey ? -10 : -1) / editor.seq.fps));
        break;
      case 'ArrowRight':
        on(() => player?.step((e.shiftKey ? 10 : 1) / editor.seq.fps));
        break;
      case 'ArrowUp':
        on(() => preview?.jumpEdit(-1));
        break;
      case 'ArrowDown':
        on(() => preview?.jumpEdit(1));
        break;
      case 'Home':
        on(() => player?.home(false));
        break;
      case 'End':
        on(() => player?.home(true));
        break;
      case 'i':
        if (onSource) on(() => editor.source && editor.setSourceIn(editor.source.playhead));
        else on(() => editor.setIn(editor.playhead));
        break;
      case 'o':
        if (onSource) on(() => editor.source && editor.setSourceOut(editor.source.playhead));
        else on(() => editor.setOut(editor.playhead));
        break;
      case 'm':
        on(() => editor.markHere());
        break;
      case 'x':
        on(() => editor.markClip());
        break;
      // Shift+, and Shift+. arrive as < and > on most layouts.
      case ',':
      case '<':
        on(() => editor.sourceEdit(e.shiftKey ? 'smart' : 'insert'));
        break;
      case '.':
      case '>':
        on(() => editor.sourceEdit(e.shiftKey ? 'append' : 'overwrite'));
        break;
      // Unshifted only: some layouts type ; and ' with Shift (German Shift+, is ;), which must not lift.
      case ';':
        if (!e.shiftKey) on(() => editor.liftOrExtract(false));
        break;
      case "'":
        if (!e.shiftKey) on(() => editor.liftOrExtract(true));
        break;
      case 'q':
        on(() => editor.trimEditToPlayhead('previous', true));
        break;
      case 'w':
        on(() => editor.trimEditToPlayhead('next', true));
        break;
      case 'e':
        on(() => editor.extendToPlayhead());
        break;
      case 'b':
        on(() => (editor.tool = 'ripple'));
        break;
      case 'n':
        on(() => (editor.tool = 'roll'));
        break;
      case 'u':
        on(() => (editor.tool = 'slide'));
        break;
      case 'v':
        on(() => (editor.tool = 'select'));
        break;
      case 'c':
        on(() => (editor.tool = 'razor'));
        break;
      case 'y':
        on(() => (editor.tool = 'slip'));
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
    ['Space', 'Play or pause'],
    ['J / K / L', 'Shuttle backwards, stop, forwards (press again: 2×, 4×, 8×)'],
    ['K + J / K + L', 'Hold K and tap J or L to step one frame'],
    ['← →', 'Step one frame (Shift: ten frames)'],
    ['↑ ↓', 'Previous or next edit point'],
    ['Home / End', 'Start or end of the sequence'],
    ['I / O', 'Mark in and out points in the focused viewer (source or program)'],
    ['⌥X', 'Clear in and out in the focused viewer'],
    ['X', 'Mark the clip under the playhead as the sequence in and out'],
    ['M', 'Add a marker in the focused viewer'],
    ['Enter / double-click', 'Open the bin item in the source viewer'],
    [', / .', 'Insert (push later clips along) or overwrite from the source'],
    ['⇧, / ⇧.', 'Smart insert at the nearest edit, or append to the end'],
    ["; / '", 'Lift (leave a gap) or extract (close it) between the sequence in and out'],
    [`${mod}U`, 'Make a subclip from the source in and out'],
    ['Q / W', 'Ripple trim the previous or next edit to the playhead'],
    ['⌥Q / ⌥W', 'Trim the previous or next edit to the playhead, leaving a gap'],
    ['E', 'Extend the selected clip’s nearest edge to the playhead'],
    ['V / C / Y', 'Selection, razor or slip tool (slip slides a clip’s content, back to its first frame)'],
    ['B / N / U', 'Ripple, roll or slide tool'],
    ['⌥⇧← →', 'Slip the focused clip’s content one frame'],
    ['S', 'Snapping on or off'],
    [`${mod}K`, 'Split at the playhead (selected clips, or every track)'],
    [`${mod}D`, 'Cross dissolve into the selected clip'],
    ['Delete / ⇧Delete', 'Delete, or ripple delete (close the gap)'],
    ['Alt-drag', 'Move without snapping'],
    [`${mod}Z / ${mac ? '⇧⌘Z' : 'Ctrl+Y'}`, 'Undo or redo'],
    ['= / - / \\', 'Zoom in, zoom out, zoom to fit'],
    ['Wheel', 'Scroll the timeline through time (Shift: scroll tracks)'],
    [`${mod}wheel / pinch`, 'Zoom the timeline at the pointer'],
    ['Drag a track’s bottom edge', 'Make that track taller or shorter (double-click resets)'],
    ['Drag the bar above the timeline', 'Give the timeline or the preview more room'],
  ];
</script>

<svelte:head><title>Editor · {PRODUCT}</title></svelte:head>
<svelte:window onkeydown={keys} onkeyup={keysUp} onblur={() => (holdingK = false)} />

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

<div class="editor" style:--timeline-h={timelineH === null ? null : `${timelineH}px`}>
  <h1 class="visually-hidden">Editor</h1>
  <div class="bar">
    <MenuBar {menus} />
    <div class="modes" role="group" aria-label="Editor mode">
      <button type="button" aria-pressed={!clipMode} onclick={() => setMode('edit')}>Edit</button>
      <button
        type="button"
        aria-pressed={clipMode}
        title="Source viewer, three-point edits, moments and silences"
        onclick={() => setMode('clip')}>Clip</button
      >
    </div>
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

  <div class="panels" class:clip={editor.mode === 'clip'} bind:this={panelsEl}>
    <MediaBin {editor} />
    {#if editor.mode === 'clip'}
      <SourceMonitor bind:this={source} {editor} onplay={() => preview?.pause()} />
    {/if}
    <Preview bind:this={preview} {editor} onplay={() => source?.pause()} />
    {#if editor.mode === 'clip'}
      <ClipPanel {editor} />
    {:else}
      <Inspector {editor} />
    {/if}
  </div>
  <div
    class="split"
    role="slider"
    tabindex="0"
    aria-label="Timeline height"
    aria-orientation="vertical"
    aria-valuemin={MIN_TIMELINE}
    aria-valuemax={Math.max(MIN_TIMELINE, shownH + Math.max(0, (panelsEl?.clientHeight ?? 0) - MIN_PANELS))}
    aria-valuenow={shownH}
    aria-valuetext="{shownH} pixels"
    title="Drag to resize the timeline and preview (double-click resets)"
    onpointerdown={startSplit}
    onpointermove={moveSplit}
    onpointerup={() => (sizing = null)}
    onpointercancel={() => (sizing = null)}
    ondblclick={() => setTimelineHeight(null)}
    onkeydown={splitKey}
  ></div>
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
    grid-template-rows: auto minmax(160px, 1fr) 6px minmax(160px, var(--timeline-h, 42vh)) auto;
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
  .modes {
    display: inline-flex;
    border: 1px solid var(--line);
    border-radius: 8px;
    overflow: hidden;
  }
  .modes button {
    font: inherit;
    font-size: 13px;
    padding: 3px 12px;
    border: 0;
    background: transparent;
    color: var(--muted);
    cursor: pointer;
  }
  .modes button + button {
    border-left: 1px solid var(--line);
  }
  .modes button[aria-pressed='true'] {
    background: var(--accent);
    color: var(--accent-ink);
    font-weight: 600;
  }
  .modes button:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: -2px;
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
  .split {
    cursor: row-resize;
    background: var(--line);
    touch-action: none;
  }
  .split:hover,
  .split:focus-visible {
    background: var(--accent);
    outline: none;
  }
  .panels {
    display: grid;
    grid-template-columns: minmax(200px, 250px) minmax(0, 1fr) minmax(230px, 280px);
    min-height: 0;
    border-bottom: 1px solid var(--line);
  }
  .panels.clip {
    grid-template-columns: minmax(180px, 220px) minmax(0, 1fr) minmax(0, 1fr) minmax(220px, 260px);
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
    .panels.clip {
      grid-template-columns: minmax(0, 1fr);
      grid-template-rows: 200px minmax(240px, 1fr) minmax(240px, 1fr) auto;
    }
    .editor {
      height: auto;
      grid-template-rows: auto auto minmax(260px, auto) auto;
    }
    .split {
      display: none;
    }
  }
</style>
