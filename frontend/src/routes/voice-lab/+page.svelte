<script lang="ts">
  import { onDestroy, onMount, tick } from 'svelte';
  import { replaceState } from '$app/navigation';
  import { PRODUCT } from '#lib/nav.ts';
  import { API, call, errorMessage, json } from '#lib/voicelab/http.ts';
  import { UrlSlots } from '#lib/voicelab/recorder.ts';
  import { kindLabel, LANG_CODES } from '#lib/voicelab/text.ts';
  import {
    bad,
    ok,
    type DescribeResult,
    type LibVoice,
    type Library,
    type MatchResult,
    type MatchStatus,
    type Msg,
    type Recipe,
  } from '#lib/voicelab/types.ts';
  import ClonePanel from './ClonePanel.svelte';

  const TABS = [
    ['library', 'Library'],
    ['design', 'Design'],
    ['describe', 'Describe'],
    ['match', 'Match'],
    ['clone', 'Clone'],
  ] as const;
  type Tab = (typeof TABS)[number][0];
  type MixRow = { key: number; id: string; weight: number };
  type Option = { recipe: Recipe; summary: string; name: string; url: string; msg: Msg };

  const urls = new UrlSlots();
  let tab = $state<Tab>('library');
  const tabEls: Partial<Record<Tab, HTMLButtonElement>> = {};

  // Library
  let voices = $state<LibVoice[]>([]);
  let languages = $state<string[]>([]);
  let q = $state('');
  let lang = $state('');
  let gender = $state('');
  let kind = $state('');
  let libMsg = $state<Msg>(ok('Loading voices…'));
  let loaded = $state(false);
  let libAudio: HTMLAudioElement | undefined = $state();
  let libUrl = $state('');
  let rowMsg = $state<Record<string, Msg>>({});
  let renaming = $state<string | null>(null);
  let newName = $state('');
  let pending = $state<Record<string, boolean>>({});

  const shown = $derived.by(() => {
    const needle = q.trim().toLowerCase();
    const list = voices.filter(
      (v) =>
        (!lang || v.language === lang) &&
        (!gender || v.gender === gender) &&
        (!kind || (kind === 'starred' ? v.starred : v.kind === kind)) &&
        (!needle || (v.name + ' ' + v.id).toLowerCase().includes(needle)),
    );
    // Starred voices float to the top; the rest keep their order.
    return list.sort((a, b) => Number(!!b.starred) - Number(!!a.starred));
  });
  const mine = $derived(voices.filter((v) => v.kind !== 'stock').length);
  const filterMsg = $derived.by((): Msg => {
    if (shown.length) return ok(`${shown.length} of ${voices.length} voices${mine ? ` (${mine} yours)` : ''}`);
    return ok(
      kind === 'starred' && !voices.some((v) => v.starred)
        ? 'No starred voices yet. Press the star next to a voice to keep it handy.'
        : kind === 'custom' && !mine
          ? 'You have no saved voices yet. Make one in Design, Describe or Match.'
          : 'No voices match these filters.',
    );
  });
  // A failure (load or star) shows until the next filter change, as the old page did.
  let libError = $state<Msg | null>(null);
  const libStatus = $derived(libError ?? (loaded ? filterMsg : libMsg));

  // Design
  let rows = $state<MixRow[]>([]);
  let nextKey = 0;
  let ctlGender = $state(0);
  let ctlGenderOut = $state('0');
  let designText = $state('Hi there. This is how I sound when I read your script out loud.');
  let designMsg = $state<Msg>(ok(''));
  let designUrl = $state('');
  let designAudio: HTMLAudioElement | undefined = $state();
  let designName = $state('');
  let designNameEl: HTMLInputElement | undefined = $state();
  let designSaveMsg = $state<Msg>(ok(''));
  let editingId: string | undefined;
  const usable = $derived(voices.filter((v) => v.kind !== 'clone'));
  const total = $derived(rows.reduce((a, r) => a + r.weight, 0));

  // Describe
  let descPrompt = $state('');
  let descGender = $state('');
  let descAccent = $state('');
  let descAge = $state('');
  let descEnergy = $state('');
  let descMsg = $state<Msg>(ok(''));
  let options = $state<Option[]>([]);
  const optionAudio: HTMLAudioElement[] = $state([]);
  const optionName: HTMLInputElement[] = $state([]);

  // Match
  let matchFile: HTMLInputElement | undefined = $state();
  let matchConsentEl: HTMLInputElement | undefined = $state();
  let matchBudget = $state('180');
  let matchConsent = $state(false);
  let matchMsg = $state<Msg>(ok(''));
  let job: string | null = null;
  let jobActive = $state(false);
  let progress = $state(0);
  let timer: ReturnType<typeof setTimeout> | undefined;
  let result = $state<MatchResult | null>(null);
  let resultJob = $state('');
  let matchName = $state('');
  let matchNameEl: HTMLInputElement | undefined = $state();
  let matchSaveMsg = $state<Msg>(ok(''));

  let busy = false;
  let destroyed = false;

  async function showTab(next: Tab, focus = false) {
    tab = next;
    if (focus) {
      await tick();
      tabEls[next]?.focus();
    }
    replaceState('#' + next, {});
  }

  function tabKey(e: KeyboardEvent, i: number) {
    const d = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
    let to: number | null = null;
    if (d) to = (i + d + TABS.length) % TABS.length;
    if (e.key === 'Home') to = 0;
    if (e.key === 'End') to = TABS.length - 1;
    if (to === null) return;
    e.preventDefault();
    void showTab(TABS[to][0], true);
  }

  async function play(slot: string, el: HTMLAudioElement | undefined, res: Response): Promise<string> {
    const url = urls.set(slot, await res.blob());
    if (el) {
      el.src = url;
      el.hidden = false;
      try {
        await el.play();
      } catch {
        // Autoplay blocked: the controls are visible.
      }
    }
    return url;
  }

  async function busyRun(key: string, fail: (m: Msg) => void, fn: () => Promise<void>) {
    if (busy) return;
    busy = true;
    pending[key] = true;
    try {
      await fn();
    } catch (e) {
      fail(bad(errorMessage(e)));
    }
    busy = false;
    pending[key] = false;
  }

  // ---------------------------------------------------------------- library
  async function loadLibrary() {
    try {
      const data = (await (await call(API + '/library')).json()) as Library;
      voices = data.voices;
      languages = data.languages;
      if (lang && !languages.includes(lang)) lang = '';
      loaded = true;
      libError = null;
      renaming = null;
      rowMsg = {};
      fillMixSelects();
    } catch (e) {
      libError = bad(errorMessage(e));
    }
  }

  function filtersChanged() {
    libError = null;
    renaming = null;
    rowMsg = {};
  }

  async function toggleStar(v: LibVoice) {
    pending['star:' + v.id] = true;
    try {
      const res = await json<{ starred: boolean }>(
        API + '/voices/' + encodeURIComponent(v.id) + '/star',
        { starred: !v.starred },
        'PUT',
      );
      v.starred = res.starred;
      pending['star:' + v.id] = false;
      await tick();
      // Starring reorders the list; keep keyboard focus on the same star.
      const again = [...document.querySelectorAll<HTMLButtonElement>('#libList .star')].find(
        (b) => b.getAttribute('aria-label') === 'Star ' + v.name,
      );
      again?.focus();
    } catch (e) {
      pending['star:' + v.id] = false;
      libError = bad(errorMessage(e));
    }
  }

  async function preview(v: LibVoice) {
    pending['pv:' + v.id] = true;
    rowMsg[v.id] = ok('Rendering…');
    try {
      const res = await call(API + '/preview?voice=' + encodeURIComponent(v.id));
      libUrl = await play('lib', libAudio, res);
      rowMsg[v.id] = ok('');
    } catch (e) {
      rowMsg[v.id] = bad(errorMessage(e));
    }
    pending['pv:' + v.id] = false;
  }

  async function copyId(v: LibVoice) {
    try {
      await navigator.clipboard.writeText(v.id);
      rowMsg[v.id] = ok('Copied.');
    } catch {
      rowMsg[v.id] = ok('Id: ' + v.id);
    }
  }

  function startRename(v: LibVoice) {
    newName = v.name;
    renaming = v.id;
  }

  async function saveName(v: LibVoice) {
    try {
      await json(API + '/voices/' + encodeURIComponent(v.id) + '/rename', { name: newName });
      await loadLibrary();
    } catch (e) {
      rowMsg[v.id] = bad(errorMessage(e));
    }
  }

  async function remove(v: LibVoice) {
    if (!confirm('Delete "' + v.name + '"? This cannot be undone.')) return;
    try {
      await call(API + '/voices/' + encodeURIComponent(v.id), { method: 'DELETE' });
      await loadLibrary();
    } catch (e) {
      rowMsg[v.id] = bad(errorMessage(e));
    }
  }

  const focusNow = (node: HTMLElement) => node.focus();

  // ---------------------------------------------------------------- design
  function addMixRow(id?: string, weight = 1) {
    if (rows.length >= 5) return;
    const valid = id && usable.some((v) => v.id === id) ? id : (usable[0]?.id ?? '');
    rows.push({ key: nextKey++, id: valid, weight });
  }

  function fillMixSelects() {
    if (!rows.length && usable.length) {
      addMixRow('af_heart', 0.6);
      addMixRow('am_michael', 0.4);
      return;
    }
    for (const r of rows) if (!usable.some((v) => v.id === r.id)) r.id = usable[0]?.id ?? '';
  }

  function addVoice() {
    const used = new Set(rows.map((r) => r.id));
    addMixRow(usable.find((v) => !used.has(v.id))?.id, 0.5);
  }

  function recipe(): Recipe {
    return { voices: rows.map((r) => ({ id: r.id, weight: r.weight })), controls: { gender: ctlGender } };
  }

  function checkMix(fail: (m: Msg) => void): Recipe | null {
    const r = recipe();
    const ids = r.voices.map((v) => v.id);
    if (new Set(ids).size !== ids.length) {
      fail(bad('Each voice can be used once in a mix.'));
      return null;
    }
    if (!r.voices.some((v) => v.weight > 0)) {
      fail(bad('Give at least one voice some weight.'));
      return null;
    }
    return r;
  }

  function designPreview() {
    const r = checkMix((m) => (designMsg = m));
    if (!r) return;
    void busyRun(
      'designPreview',
      (m) => (designMsg = m),
      async () => {
        designMsg = ok('Rendering preview (a few seconds)…');
        const res = await call(API + '/design/preview', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ recipe: r, text: designText }),
        });
        designUrl = await play('design', designAudio, res);
        designMsg = ok('Preview ready.');
      },
    );
  }

  function designSave() {
    const r = checkMix((m) => (designSaveMsg = m));
    if (!r) return;
    if (!designName.trim()) {
      designSaveMsg = bad('Give the voice a name first.');
      designNameEl?.focus();
      return;
    }
    void busyRun(
      'designSave',
      (m) => (designSaveMsg = m),
      async () => {
        const rec = await json<{ name: string }>(API + '/design/save', { recipe: r, name: designName, kind: 'blend' });
        designSaveMsg = ok('Saved "' + rec.name + '" to your library' + (editingId ? ' as a new version.' : '.'));
        await loadLibrary();
      },
    );
  }

  function openRecipe(v: { id?: string; name: string; meta?: { recipe?: Recipe } }) {
    const rcp = v.meta?.recipe;
    if (!rcp) return;
    rows = [];
    for (const x of rcp.voices.slice(0, 5)) addMixRow(x.id, x.weight);
    while (rows.length < 2) addMixRow();
    ctlGender = rcp.controls?.gender || 0;
    ctlGenderOut = ctlGender.toFixed(2);
    designName = v.name;
    editingId = v.id;
    designSaveMsg = ok('Editing "' + v.name + '". Saving keeps the original and adds the new version.');
    void showTab('design', true);
  }

  // ---------------------------------------------------------------- describe
  function describe() {
    const body = { prompt: descPrompt, gender: descGender, accent: descAccent, age: descAge, energy: descEnergy };
    if (!body.prompt.trim() && !body.gender && !body.accent && !body.age && !body.energy) {
      descMsg = bad('Describe the voice or pick at least one option.');
      return;
    }
    void busyRun(
      'descGo',
      (m) => (descMsg = m),
      async () => {
        descMsg = ok('Picking voices…');
        const out = await json<DescribeResult>(API + '/describe', body);
        descMsg = ok(
          (out.understood.length
            ? 'Understood: ' + out.understood.join(', ') + '.'
            : 'No keywords recognised; these are general picks.') + (out.notes.length ? ' ' + out.notes.join(' ') : ''),
        );
        for (let i = 0; i < options.length; i++) urls.revoke('opt' + i);
        options = out.options.map((o) => ({ recipe: o.recipe, summary: o.summary, name: '', url: '', msg: ok('') }));
      },
    );
  }

  function playOption(o: Option, i: number) {
    void busyRun(
      'play' + i,
      (m) => (o.msg = m),
      async () => {
        o.msg = ok('Rendering…');
        const res = await call(API + '/design/preview', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ recipe: o.recipe, text: designText }),
        });
        o.url = await play('opt' + i, optionAudio[i], res);
        o.msg = ok('');
      },
    );
  }

  function saveOption(o: Option, i: number) {
    if (!o.name.trim()) {
      o.msg = bad('Give the voice a name first.');
      optionName[i]?.focus();
      return;
    }
    void busyRun(
      'save' + i,
      (m) => (o.msg = m),
      async () => {
        const rec = await json<{ name: string }>(API + '/design/save', {
          recipe: o.recipe,
          name: o.name,
          kind: 'describe',
        });
        o.msg = ok('Saved "' + rec.name + '".');
        await loadLibrary();
      },
    );
  }

  // ---------------------------------------------------------------- match
  function startMatch() {
    const f = matchFile?.files?.[0];
    if (!f) {
      matchMsg = bad('Choose a recording first.');
      matchFile?.focus();
      return;
    }
    if (f.size > 100 * 1024 * 1024) {
      matchMsg = bad('That file is over 100 MB.');
      return;
    }
    if (!matchConsent) {
      matchMsg = bad('Confirm that you own this voice or have permission to use it.');
      matchConsentEl?.focus();
      return;
    }
    const fd = new FormData();
    fd.append('file', f);
    fd.append('consent', 'true');
    fd.append('budget', matchBudget);
    result = null;
    void busyRun(
      'matchGo',
      (m) => (matchMsg = m),
      async () => {
        matchMsg = ok('Uploading…');
        const out = (await (await call(API + '/match', { method: 'POST', body: fd })).json()) as { job: string };
        job = out.job;
        progress = 0;
        jobActive = true;
        void poll();
      },
    );
  }

  async function poll() {
    clearTimeout(timer);
    if (destroyed || !job) return;
    try {
      const st = (await (await call(API + '/match/' + job)).json()) as MatchStatus;
      progress = Math.round(100 * (st.progress || 0));
      if (st.status === 'running') {
        matchMsg = ok(
          (st.step ?? '') +
            (st.similarity != null ? ' · best similarity ' + st.similarity.toFixed(3) : '') +
            ' · ' +
            Math.round(st.elapsed) +
            ' s',
        );
        if (!destroyed) timer = setTimeout(() => void poll(), 1000);
        return;
      }
      jobActive = false;
      if (st.status === 'done' && st.result) showResult(st.result, job);
      else if (st.status === 'cancelled') matchMsg = ok('Cancelled. Nothing was saved.');
      else matchMsg = bad(st.error || 'Matching failed.');
    } catch (e) {
      jobActive = false;
      matchMsg = bad(errorMessage(e));
    }
  }

  async function cancelMatch() {
    if (!job) return;
    matchMsg = ok('Cancelling…');
    try {
      await call(API + '/match/' + job + '/cancel', { method: 'POST' });
    } catch (e) {
      matchMsg = bad(errorMessage(e));
    }
  }

  function showResult(r: MatchResult, id: string) {
    matchMsg = ok('Done in ' + Math.round(r.seconds) + ' s: ' + r.tries + ' tries, ' + r.kept + ' kept.');
    resultJob = id;
    result = r;
  }

  function saveMatch() {
    if (!matchName.trim()) {
      matchSaveMsg = bad('Give the voice a name first.');
      matchNameEl?.focus();
      return;
    }
    void busyRun(
      'matchSave',
      (m) => (matchSaveMsg = m),
      async () => {
        const rec = await json<{ name: string }>(API + '/match/' + job + '/save', { name: matchName });
        matchSaveMsg = ok('Saved "' + rec.name + '" to your library.');
        await loadLibrary();
      },
    );
  }

  const matchAudio = (which: string) => `${API}/match/${resultJob}/audio?which=${which}`;

  onMount(() => {
    const start = TABS.find(([id]) => '#' + id === location.hash);
    if (start) tab = start[0];
    void loadLibrary();
  });

  onDestroy(() => {
    destroyed = true;
    clearTimeout(timer);
    urls.dispose();
  });
</script>

<svelte:head><title>Voice Lab · {PRODUCT}</title></svelte:head>

<div class="vl">
  <h1>Voice Lab</h1>
  <p><a href="/samples" data-sveltekit-reload>Voice sample collections</a></p>
  <p class="lede">
    Browse every voice, mix new ones, describe a voice in words, or match one from a recording. Everything runs on this
    computer.
  </p>
  <div class="tabs" role="tablist" aria-label="Voice Lab sections">
    {#each TABS as [id, label], i (id)}
      <button
        role="tab"
        id={'tab-' + id}
        aria-controls={id}
        aria-selected={tab === id}
        tabindex={tab === id ? 0 : -1}
        bind:this={tabEls[id]}
        onclick={() => void showTab(id)}
        onkeydown={(e) => tabKey(e, i)}>{label}</button
      >
    {/each}
  </div>

  <div id="library" role="tabpanel" aria-labelledby="tab-library" class="card" hidden={tab !== 'library'}>
    <h2>Library</h2>
    <div class="filters">
      <label
        >Search<input
          type="text"
          id="libSearch"
          placeholder="Name or id"
          autocomplete="off"
          bind:value={q}
          oninput={filtersChanged}
        /></label
      >
      <label
        >Language<select id="libLang" bind:value={lang} onchange={filtersChanged}
          ><option value="">All languages</option>{#each languages as l (l)}<option value={l}>{l}</option
            >{/each}</select
        ></label
      >
      <label
        >Gender<select id="libGender" bind:value={gender} onchange={filtersChanged}
          ><option value="">Any</option><option value="female">Female</option><option value="male">Male</option></select
        ></label
      >
      <label
        >Kind<select id="libKind" bind:value={kind} onchange={filtersChanged}
          ><option value="">All voices</option><option value="starred">★ Starred</option><option value="stock"
            >Stock</option
          ><option value="custom">My voices</option><option value="clone">Clones</option></select
        ></label
      >
    </div>
    <p class="status" class:error={libStatus.bad} id="libStatus" role="status">{libStatus.text}</p>
    <audio id="libAudio" controls hidden={!libUrl} bind:this={libAudio}></audio>
    <ul class="voices" id="libList">
      {#each shown as v (v.id)}
        {@const msg = rowMsg[v.id]}
        <li>
          <div class="who">
            <button
              class="star"
              class:on={v.starred}
              type="button"
              aria-pressed={!!v.starred}
              aria-label={'Star ' + v.name}
              title={v.starred ? 'Remove star' : 'Star this voice'}
              disabled={pending['star:' + v.id]}
              onclick={() => void toggleStar(v)}>{v.starred ? '\u2605' : '\u2606'}</button
            ><strong>{v.name}</strong><span class="hint">{v.id + ' '}</span><span
              ><span class="tag">{kindLabel(v.kind)}</span>{#if v.language}<span class="tag">{v.language}</span
                >{/if}{#if v.gender && v.gender !== 'unknown'}<span class="tag">{v.gender}</span>{/if}</span
            >
          </div>
          <div>
            <div class="row">
              {#if renaming === v.id}
                <input
                  type="text"
                  maxlength="60"
                  aria-label="New name"
                  bind:value={newName}
                  {@attach focusNow}
                  onkeydown={(e) => {
                    if (e.key === 'Enter') void saveName(v);
                    if (e.key === 'Escape') renaming = null;
                  }}
                />
                <button class="btn small" type="button" onclick={() => void saveName(v)}>Save name</button>
              {:else}
                {#if v.kind !== 'clone'}
                  <button
                    class="btn small"
                    type="button"
                    aria-label={'Preview ' + v.name}
                    disabled={pending['pv:' + v.id]}
                    onclick={() => void preview(v)}>Preview</button
                  >
                {/if}
                <button
                  class="btn secondary small"
                  type="button"
                  aria-label={'Copy id of ' + v.name}
                  onclick={() => void copyId(v)}>Copy id</button
                >
                <a class="btn secondary small" href={'/studio?voice=' + encodeURIComponent(v.id)} data-sveltekit-reload
                  >Use in Studio</a
                >
                {#if v.editable}
                  <button class="btn secondary small" type="button" onclick={() => openRecipe(v)}>Edit</button>
                {/if}
                {#if v.kind !== 'stock'}
                  <button
                    class="btn secondary small"
                    type="button"
                    aria-label={'Rename ' + v.name}
                    onclick={() => startRename(v)}>Rename</button
                  >
                  <button
                    class="btn danger small"
                    type="button"
                    aria-label={'Delete ' + v.name}
                    onclick={() => void remove(v)}>Delete</button
                  >
                {/if}
              {/if}
            </div>
            <span class="hint" class:error={msg?.bad} role="status">{msg?.text ?? ''}</span>
          </div>
        </li>
      {/each}
    </ul>
  </div>

  <div id="design" role="tabpanel" aria-labelledby="tab-design" class="card" hidden={tab !== 'design'}>
    <h2>Design a voice</h2>
    <p class="hint">Mix 2 to 5 voices. Weights are shares of the mix and always add up to 100%.</p>
    <div id="mixRows">
      {#each rows as r, i (r.key)}
        <div class="mix">
          <select aria-label={'Voice ' + (i + 1)} bind:value={r.id}>
            {#each usable as v (v.id)}
              <option value={v.id}>{v.name + (v.kind === 'stock' ? ` (${v.language}, ${v.gender})` : ' (mine)')}</option
              >
            {/each}
          </select>
          <input
            type="range"
            min="0"
            max="1"
            step="0.01"
            aria-label={'Weight of voice ' + (i + 1)}
            bind:value={r.weight}
          />
          <output>{total ? Math.round((100 * r.weight) / total) + '%' : '–'}</output>
          <button
            class="btn secondary small"
            type="button"
            aria-label={'Remove voice ' + (i + 1)}
            disabled={rows.length <= 2}
            onclick={() => {
              if (rows.length > 2) rows.splice(i, 1);
            }}>Remove</button
          >
        </div>
      {/each}
    </div>
    <p>
      <button class="btn secondary small" id="addVoice" type="button" disabled={rows.length >= 5} onclick={addVoice}
        >Add a voice</button
      >
    </p>
    <div class="field">
      <label for="ctlGender">Masculine ↔ Feminine</label>
      <div class="ctl">
        <input
          type="range"
          id="ctlGender"
          min="-1"
          max="1"
          step="0.05"
          bind:value={ctlGender}
          oninput={() => (ctlGenderOut = ctlGender.toFixed(2))}
        /><output id="ctlGenderOut" for="ctlGender">{ctlGenderOut}</output>
      </div>
      <span class="hint"
        >Moves along the average difference between Kokoro's female and male voices. Right raises the pitch (about +30
        Hz at full strength), left lowers it.</span
      >
    </div>
    <div class="field">
      <label for="designText">Preview line</label>
      <textarea id="designText" rows="2" maxlength="300" bind:value={designText}></textarea>
    </div>
    <div class="row">
      <button class="btn" id="designPreview" type="button" disabled={pending.designPreview} onclick={designPreview}
        >Preview</button
      >
      <span class="status" class:error={designMsg.bad} id="designStatus" role="status">{designMsg.text}</span>
    </div>
    <audio id="designAudio" controls hidden={!designUrl} bind:this={designAudio}></audio>
    <div class="row" style="margin-top:12px">
      <label for="designName" class="hint">Name</label><input
        type="text"
        id="designName"
        maxlength="60"
        placeholder="e.g. Warm narrator"
        bind:value={designName}
        bind:this={designNameEl}
      />
      <button class="btn secondary" id="designSave" type="button" disabled={pending.designSave} onclick={designSave}
        >Save voice</button
      >
    </div>
    <p class="status" class:error={designSaveMsg.bad} id="designSaveStatus" role="status">{designSaveMsg.text}</p>
  </div>

  <div id="describe" role="tabpanel" aria-labelledby="tab-describe" class="card" hidden={tab !== 'describe'}>
    <h2>Describe a voice</h2>
    <p class="note">
      This is keyword-based voice design, not a generative model. Words like <em>deep, bright, warm, British, female</em
      > pick matching stock voices (by tags and measured pitch and brightness) and mix them with a little random variation.
    </p>
    <div class="field">
      <label for="descPrompt">Description</label>
      <textarea
        id="descPrompt"
        rows="2"
        maxlength="300"
        placeholder="warm, deep male narrator, British"
        bind:value={descPrompt}></textarea>
    </div>
    <div class="filters">
      <label
        >Gender<select id="descGender" bind:value={descGender}
          ><option value="">From description</option><option value="female">Female</option><option value="male"
            >Male</option
          ></select
        ></label
      >
      <label
        >Accent / language<select id="descAccent" bind:value={descAccent}
          ><option value="">From description</option>{#each LANG_CODES as [code, name] (code)}<option value={code}
              >{name}</option
            >{/each}</select
        ></label
      >
      <label
        >Age feel<select id="descAge" bind:value={descAge}
          ><option value="">Any</option><option value="young">Young (higher)</option><option value="adult">Adult</option
          ><option value="older">Older (lower)</option></select
        ></label
      >
      <label
        >Energy<select id="descEnergy" bind:value={descEnergy}
          ><option value="">Any</option><option value="calm">Calm (warmer)</option><option value="neutral"
            >Neutral</option
          ><option value="energetic">Energetic (brighter)</option></select
        ></label
      >
    </div>
    <div class="row">
      <button class="btn" id="descGo" type="button" disabled={pending.descGo} onclick={describe}
        >Generate 3 options</button
      >
      <span class="status" class:error={descMsg.bad} id="descStatus" role="status">{descMsg.text}</span>
    </div>
    <div class="options" id="descOptions">
      {#each options as o, i (o)}
        <div class="option">
          <strong>Option {i + 1}</strong>
          <span class="hint">{o.summary}</span>
          <div class="row">
            <button class="btn small" type="button" disabled={pending['play' + i]} onclick={() => playOption(o, i)}
              >Play option {i + 1}</button
            >
          </div>
          <audio controls hidden={!o.url} bind:this={optionAudio[i]}></audio>
          <div class="row">
            <input
              type="text"
              maxlength="60"
              placeholder="Name"
              aria-label={'Name for option ' + (i + 1)}
              bind:value={o.name}
              bind:this={optionName[i]}
            />
            <button
              class="btn secondary small"
              type="button"
              disabled={pending['save' + i]}
              onclick={() => saveOption(o, i)}>Save</button
            >
          </div>
          <button
            class="btn secondary small"
            type="button"
            onclick={() => openRecipe({ name: o.name || 'Option ' + (i + 1), meta: { recipe: o.recipe } })}
            >Fine-tune in Design</button
          >
          <p class="status" class:error={o.msg.bad} role="status">{o.msg.text}</p>
        </div>
      {/each}
    </div>
  </div>

  <div id="match" role="tabpanel" aria-labelledby="tab-match" class="card" hidden={tab !== 'match'}>
    <h2>Match a voice from a recording</h2>
    <p class="note">
      This approximates the recording's timbre using only Kokoro's built-in voice space. The result is the closest blend
      of the built-in voices, not a true clone: accent, rhythm and many details won't carry over. For a true clone of
      the recording, <button type="button" class="linkish" id="goClone" onclick={() => void showTab('clone', true)}
        >use the Clone tab</button
      >.
    </p>
    <div class="field">
      <label for="matchFile"
        >Reference recording (10–60 seconds of one speaker; WAV, MP3, M4A or MP4, up to 100 MB)</label
      >
      <input type="file" id="matchFile" accept=".wav,.mp3,.m4a,.mp4,audio/*,video/mp4" bind:this={matchFile} />
    </div>
    <div class="field">
      <label for="matchBudget">Search time</label>
      <select id="matchBudget" bind:value={matchBudget}
        ><option value="60">1 minute (rough)</option><option value="180">3 minutes</option><option value="300"
          >5 minutes</option
        ><option value="600">10 minutes (best)</option></select
      >
      <span class="hint">Each try renders a 14-second test line, about 13 seconds per try on a typical laptop CPU.</span
      >
    </div>
    <p>
      <label
        ><input type="checkbox" id="matchConsent" bind:checked={matchConsent} bind:this={matchConsentEl} /> I own this voice
        or have permission to use it.</label
      >
    </p>
    <div class="row">
      <button class="btn" id="matchGo" type="button" disabled={pending.matchGo || jobActive} onclick={startMatch}
        >Start matching</button
      >
      <button
        class="btn secondary"
        id="matchCancel"
        type="button"
        hidden={!jobActive}
        onclick={() => void cancelMatch()}>Cancel</button
      >
    </div>
    <p class="status" class:error={matchMsg.bad} id="matchStatus" role="status">{matchMsg.text}</p>
    <div class="bar" id="matchBar" hidden={!jobActive}><span style:width={progress + '%'}></span></div>
    <div id="matchResult" hidden={!result}>
      <h3>Result</h3>
      <div class="scores">
        <div class="score">
          <span class="hint">Starting blend</span><b id="simBefore">{result?.before.toFixed(3) ?? '–'}</b>
        </div>
        <div class="score">
          <span class="hint">After search</span><b id="simAfter">{result?.after.toFixed(3) ?? '–'}</b>
        </div>
        <div class="score">
          <span class="hint">Closest stock voices</span><span id="simStock"
            >{#each result?.best_stock ?? [] as s (s.id)}<span class="tag">{s.id + ' ' + s.similarity.toFixed(2)}</span
              >{/each}</span
          >
        </div>
      </div>
      <p class="hint">
        Scores are cosine similarity between speaker embeddings (1 = same voice). On this engine the same stock voice
        reading two different texts scores about 0.3–0.95, while different voices mostly score below 0.45, so treat the
        number as a guide rather than proof.
      </p>
      <div class="players">
        {#each [['playRef', 'reference', 'Your recording'], ['playBefore', 'before', 'Before (starting blend)'], ['playAfter', 'after', 'After search']] as [id, which, label] (id)}
          <div class="player">
            <span id={id + 'Label'}>{label}</span><audio
              {id}
              controls
              preload="none"
              aria-labelledby={id + 'Label'}
              src={result ? matchAudio(which) : undefined}
            ></audio>
          </div>
        {/each}
      </div>
      <div class="row" style="margin-top:12px">
        <label for="matchName" class="hint">Name</label>
        <input
          type="text"
          id="matchName"
          maxlength="60"
          placeholder="e.g. Matched narrator"
          bind:value={matchName}
          bind:this={matchNameEl}
        />
        <button class="btn secondary" id="matchSave" type="button" disabled={pending.matchSave} onclick={saveMatch}
          >Save voice</button
        >
      </div>
      <p class="status" class:error={matchSaveMsg.bad} id="matchSaveStatus" role="status">{matchSaveMsg.text}</p>
    </div>
  </div>

  <div id="clone" role="tabpanel" aria-labelledby="tab-clone" hidden={tab !== 'clone'}>
    <p><a class="btn secondary" href="/samples" data-sveltekit-reload>Build a voice sample collection</a></p>
    <ClonePanel />
  </div>
</div>

<style>
  /* Global under .vl so the cloning panel inherits these rules exactly as on the old page. */
  .vl :global {
    .tabs {
      display: flex;
      gap: 4px;
      flex-wrap: wrap;
      margin: 0 0 16px;
      border-bottom: 1px solid var(--line);
    }
    .tabs button {
      font: inherit;
      font-weight: 600;
      background: none;
      border: 0;
      color: var(--muted);
      padding: 10px 14px;
      cursor: pointer;
      border-radius: 8px 8px 0 0;
    }
    .tabs button[aria-selected='true'] {
      color: var(--ink);
      box-shadow: inset 0 -2px 0 var(--accent);
    }
    .row {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      align-items: center;
    }
    .row > * {
      min-width: 0;
    }
    .filters {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 10px;
      margin-bottom: 12px;
    }
    .filters label,
    .field {
      display: flex;
      flex-direction: column;
      gap: 4px;
      font-size: 0.9rem;
    }
    .field {
      margin-bottom: 12px;
    }
    .voices {
      list-style: none;
      margin: 0;
      padding: 0;
    }
    .voices li {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      padding: 10px 0;
      border-top: 1px solid var(--line);
    }
    .voices .who {
      min-width: 0;
      overflow-wrap: anywhere;
    }
    .voices .who strong {
      display: inline;
    }
    .voices .who .hint {
      display: block;
      margin-top: 2px;
    }
    .tag {
      display: inline-block;
      font-size: 0.78rem;
      color: var(--muted);
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 1px 8px;
      margin: 2px 4px 0 0;
    }
    .star {
      vertical-align: middle;
      background: none;
      border: 0;
      font-size: 1.25rem;
      line-height: 1;
      cursor: pointer;
      color: var(--muted);
      padding: 2px 6px;
      margin-right: 4px;
      border-radius: 6px;
    }
    .star.on {
      color: var(--warn);
    }
    .star:hover {
      color: var(--ink);
    }
    .btn.small {
      padding: 6px 10px;
      font-size: 0.9rem;
    }
    .mix {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr) 3.5em auto;
      gap: 8px;
      align-items: center;
      margin-bottom: 8px;
    }
    .mix select {
      width: 100%;
    }
    .mix output,
    .ctl output {
      font-variant-numeric: tabular-nums;
      text-align: right;
    }
    .ctl {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 3.5em;
      gap: 8px;
      align-items: center;
    }
    input[type='range'] {
      width: 100%;
    }
    textarea {
      width: 100%;
    }
    .options {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 12px;
    }
    .option {
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 12px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    audio {
      width: 100%;
      max-width: 420px;
    }
    .bar {
      height: 8px;
      background: var(--line);
      border-radius: 99px;
      overflow: hidden;
    }
    .bar span {
      display: block;
      height: 100%;
      width: 0;
      background: var(--accent);
      transition: width var(--motion-progress) var(--motion-easing);
    }
    .scores {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 10px;
    }
    .score {
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 10px;
    }
    .score b {
      font-size: 1.4rem;
      display: block;
    }
    .note {
      background: var(--bg);
      border-left: 3px solid var(--warn);
      padding: 8px 12px;
      border-radius: 6px;
      font-size: 0.92rem;
    }
    .linkish {
      font: inherit;
      background: none;
      border: 0;
      padding: 0;
      color: var(--accent);
      text-decoration: underline;
      cursor: pointer;
    }
    .players {
      display: grid;
      gap: 8px;
    }
    @media (max-width: 520px) {
      .mix {
        grid-template-columns: minmax(0, 1fr) 3.5em auto;
      }
      .mix input[type='range'] {
        grid-column: 1 / -1;
        grid-row: 2;
      }
    }
  }
</style>
