// Voice Lab page. All user/voice text goes through textContent (never innerHTML).
(() => {
  'use strict';
  /** @template {string} K
   * @param {K} id
   * @returns {import('../../../types/dom').ElementFor<import('../../../types/dom').VoiceLabElements, K>}
   */
  const $ = (id) =>
    /** @type {import('../../../types/dom').ElementFor<import('../../../types/dom').VoiceLabElements, K>} */ (
      document.getElementById(id)
    );
  const API = '/api/voicelab';
  const LANG_CODES = {
    a: 'American English',
    b: 'British English',
    e: 'Spanish',
    f: 'French',
    h: 'Hindi',
    i: 'Italian',
    p: 'Brazilian Portuguese',
    j: 'Japanese',
    z: 'Mandarin Chinese',
  };
  let voices = [];
  let busy = false;

  function el(tag, props = {}, ...kids) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
      if (k === 'class') n.className = v;
      else if (k === 'text') n.textContent = v;
      else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v);
    }
    for (const kid of kids) if (kid != null) n.append(kid);
    return n;
  }

  async function errorText(res) {
    if (res.status === 429)
      return 'Another voice job is running on this computer. Wait for it to finish, then try again.';
    try {
      const j = await res.json();
      if (typeof j.detail === 'string') return j.detail;
      if (Array.isArray(j.detail) && j.detail[0])
        return 'Check the inputs: ' + (j.detail[0].msg || 'invalid value') + '.';
    } catch {
      /* not JSON */
    }
    return 'Something went wrong (' + res.status + '). Try again.';
  }

  async function call(url, opts = {}) {
    let res;
    try {
      res = await fetch(url, opts);
    } catch (cause) {
      throw new Error('Could not reach Voice Studio. Is the app still running?', { cause });
    }
    if (!res.ok) throw new Error(await errorText(res));
    return res;
  }
  const json = (url, body, method = 'POST') =>
    call(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).then((r) => r.json());

  function say(node, msg, bad = false) {
    node.textContent = msg;
    node.classList.toggle('error', bad);
  }

  async function playBlob(audioEl, res) {
    const blob = await res.blob();
    if (audioEl.dataset.url) URL.revokeObjectURL(audioEl.dataset.url);
    const url = URL.createObjectURL(blob);
    audioEl.dataset.url = url;
    audioEl.src = url;
    audioEl.hidden = false;
    try {
      await audioEl.play();
    } catch {
      /* autoplay blocked: controls are visible */
    }
  }

  // ---------------------------------------------------------------- tabs
  const tabs = [.../** @type {NodeListOf<HTMLButtonElement>} */ (document.querySelectorAll('[role=tab]'))];
  function showTab(tab, focus = false) {
    for (const t of tabs) {
      const on = t === tab;
      t.setAttribute('aria-selected', String(on));
      t.tabIndex = on ? 0 : -1;
      $(t.getAttribute('aria-controls')).hidden = !on;
    }
    if (focus) tab.focus();
    history.replaceState(null, '', '#' + tab.getAttribute('aria-controls'));
  }
  tabs.forEach((t, i) => {
    t.addEventListener('click', () => showTab(t));
    t.addEventListener('keydown', (e) => {
      const d = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
      if (d) {
        e.preventDefault();
        showTab(tabs[(i + d + tabs.length) % tabs.length], true);
      }
      if (e.key === 'Home') {
        e.preventDefault();
        showTab(tabs[0], true);
      }
      if (e.key === 'End') {
        e.preventDefault();
        showTab(tabs[tabs.length - 1], true);
      }
    });
  });
  const start = tabs.find((t) => '#' + t.getAttribute('aria-controls') === location.hash);
  if (start) showTab(start);

  // ---------------------------------------------------------------- library
  const libStatus = $('libStatus'),
    libList = $('libList'),
    libAudio = $('libAudio');

  async function loadLibrary() {
    try {
      const data = await call(API + '/library').then((r) => r.json());
      voices = data.voices;
      const sel = $('libLang'),
        keep = sel.value;
      sel.replaceChildren(
        el('option', { value: '', text: 'All languages' }),
        ...data.languages.map((l) => el('option', { value: l, text: l })),
      );
      sel.value = keep;
      renderLibrary();
      fillMixSelects();
    } catch (e) {
      say(libStatus, e.message, true);
    }
  }

  function renderLibrary() {
    const q = $('libSearch').value.trim().toLowerCase();
    const lang = $('libLang').value,
      g = $('libGender').value,
      kind = $('libKind').value;
    const shown = voices.filter(
      (v) =>
        (!lang || v.language === lang) &&
        (!g || v.gender === g) &&
        (!kind || (kind === 'starred' ? v.starred : v.kind === kind)) &&
        (!q || (v.name + ' ' + v.id).toLowerCase().includes(q)),
    );
    const mine = voices.filter((v) => v.kind !== 'stock').length;
    if (!shown.length) {
      say(
        libStatus,
        kind === 'starred' && !voices.some((v) => v.starred)
          ? 'No starred voices yet. Press the star next to a voice to keep it handy.'
          : kind === 'custom' && !mine
            ? 'You have no saved voices yet. Make one in Design, Describe or Match.'
            : 'No voices match these filters.',
      );
    } else {
      say(libStatus, shown.length + ' of ' + voices.length + ' voices' + (mine ? ' (' + mine + ' yours)' : ''));
    }
    // Starred voices float to the top; the rest keep their order.
    shown.sort((a, b) => Number(!!b.starred) - Number(!!a.starred));
    libList.replaceChildren(...shown.map(voiceRow));
  }

  function voiceRow(v) {
    const tags = el(
      'span',
      {},
      ...[
        v.kind === 'stock' ? 'Stock' : v.kind === 'clone' ? 'Clone' : 'Mine',
        v.language,
        v.gender !== 'unknown' ? v.gender : null,
      ]
        .filter(Boolean)
        .map((t) => el('span', { class: 'tag', text: t })),
    );
    const star = el('button', {
      class: 'star' + (v.starred ? ' on' : ''),
      type: 'button',
      text: v.starred ? '\u2605' : '\u2606',
      'aria-pressed': String(!!v.starred),
      'aria-label': 'Star ' + v.name,
      title: v.starred ? 'Remove star' : 'Star this voice',
    });
    star.addEventListener('click', async () => {
      star.disabled = true;
      try {
        const res = await json(API + '/voices/' + encodeURIComponent(v.id) + '/star', { starred: !v.starred }, 'PUT');
        v.starred = res.starred;
        renderLibrary();
        const again = [.../** @type {NodeListOf<HTMLButtonElement>} */ (libList.querySelectorAll('.star'))].find(
          (b) => b.getAttribute('aria-label') === 'Star ' + v.name,
        );
        if (again) again.focus();
      } catch (e) {
        star.disabled = false;
        say(libStatus, e.message, true);
      }
    });
    const who = el(
      'div',
      { class: 'who' },
      star,
      el('strong', { text: v.name }),
      el('span', { class: 'hint', text: v.id + ' ' }),
      tags,
    );
    const status = el('span', { class: 'hint', role: 'status' });
    const acts = el('div', { class: 'row' });
    if (v.kind !== 'clone') {
      const pv = el('button', {
        class: 'btn small',
        type: 'button',
        text: 'Preview',
        'aria-label': 'Preview ' + v.name,
      });
      pv.addEventListener('click', async () => {
        pv.disabled = true;
        say(status, 'Rendering…');
        try {
          const res = await call(API + '/preview?voice=' + encodeURIComponent(v.id));
          await playBlob(libAudio, res);
          say(status, '');
        } catch (e) {
          say(status, e.message, true);
        }
        pv.disabled = false;
      });
      acts.append(pv);
    }
    const copy = el('button', {
      class: 'btn secondary small',
      type: 'button',
      text: 'Copy id',
      'aria-label': 'Copy id of ' + v.name,
    });
    copy.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(v.id);
        say(status, 'Copied.');
      } catch {
        say(status, 'Id: ' + v.id);
      }
    });
    acts.append(
      copy,
      el('a', {
        class: 'btn secondary small',
        href: 'studio.html?voice=' + encodeURIComponent(v.id),
        text: 'Use in Studio',
      }),
    );
    if (v.editable) {
      acts.append(
        el('button', { class: 'btn secondary small', type: 'button', text: 'Edit', onclick: () => openRecipe(v) }),
      );
    }
    if (v.kind !== 'stock') {
      const ren = el('button', {
        class: 'btn secondary small',
        type: 'button',
        text: 'Rename',
        'aria-label': 'Rename ' + v.name,
      });
      ren.addEventListener('click', () => {
        const input = el('input', { type: 'text', maxlength: '60', 'aria-label': 'New name' });
        input.value = v.name;
        const ok = el('button', { class: 'btn small', type: 'button', text: 'Save name' });
        const go = async () => {
          try {
            await json(API + '/voices/' + encodeURIComponent(v.id) + '/rename', { name: input.value });
            await loadLibrary();
          } catch (e) {
            say(status, e.message, true);
          }
        };
        ok.addEventListener('click', go);
        input.addEventListener('keydown', (e) => {
          if (e.key === 'Enter') go();
          if (e.key === 'Escape') renderLibrary();
        });
        acts.replaceChildren(input, ok);
        input.focus();
      });
      const del = el('button', {
        class: 'btn danger small',
        type: 'button',
        text: 'Delete',
        'aria-label': 'Delete ' + v.name,
      });
      del.addEventListener('click', async () => {
        if (!confirm('Delete "' + v.name + '"? This cannot be undone.')) return;
        try {
          await call(API + '/voices/' + encodeURIComponent(v.id), { method: 'DELETE' });
          await loadLibrary();
        } catch (e) {
          say(status, e.message, true);
        }
      });
      acts.append(ren, del);
    }
    return el('li', {}, who, el('div', {}, acts, status));
  }

  for (const id of ['libSearch', 'libLang', 'libGender', 'libKind']) $(id).addEventListener('input', renderLibrary);

  // ---------------------------------------------------------------- design
  const mixRows = $('mixRows');
  let editingId = null;

  function usable() {
    return voices.filter((v) => v.kind !== 'clone');
  }

  function addMixRow(id, weight = 1) {
    if (mixRows.children.length >= 5) return;
    const n = mixRows.children.length + 1;
    const sel = el('select', { 'aria-label': 'Voice ' + n });
    const rng = el('input', { type: 'range', min: '0', max: '1', step: '0.01', 'aria-label': 'Weight of voice ' + n });
    rng.value = String(weight);
    const out = el('output');
    const rm = el('button', {
      class: 'btn secondary small',
      type: 'button',
      text: 'Remove',
      'aria-label': 'Remove voice ' + n,
    });
    rm.addEventListener('click', () => {
      if (mixRows.children.length > 2) {
        row.remove();
        updateMix();
      }
    });
    const row = el('div', { class: 'mix' }, sel, rng, out, rm);
    rng.addEventListener('input', updateMix);
    sel.addEventListener('change', updateMix);
    mixRows.append(row);
    fillSelect(sel, id);
    updateMix();
  }

  function fillSelect(sel, want) {
    const cur = want || sel.value;
    sel.replaceChildren(
      ...usable().map((v) =>
        el('option', {
          value: v.id,
          text: v.name + (v.kind === 'stock' ? ' (' + v.language + ', ' + v.gender + ')' : ' (mine)'),
        }),
      ),
    );
    if (cur && usable().some((v) => v.id === cur)) sel.value = cur;
  }

  function fillMixSelects() {
    if (!mixRows.children.length && usable().length) {
      addMixRow('af_heart', 0.6);
      addMixRow('am_michael', 0.4);
    } else for (const s of mixRows.querySelectorAll('select')) fillSelect(s);
  }

  function updateMix() {
    const rows = [...mixRows.children];
    const ws = rows.map((r) => Number(r.querySelector('input').value));
    const total = ws.reduce((a, b) => a + b, 0);
    rows.forEach((r, i) => {
      r.querySelector('output').textContent = total ? Math.round((100 * ws[i]) / total) + '%' : '–';
    });
    rows.forEach((r) => {
      r.querySelector('button').disabled = rows.length <= 2;
    });
    $('addVoice').disabled = rows.length >= 5;
  }

  function recipe() {
    return {
      voices: [...mixRows.children].map((r) => ({
        id: r.querySelector('select').value,
        weight: Number(r.querySelector('input').value),
      })),
      controls: { gender: Number($('ctlGender').value) },
    };
  }

  function checkMix(statusEl) {
    const r = recipe();
    const ids = r.voices.map((v) => v.id);
    if (new Set(ids).size !== ids.length) {
      say(statusEl, 'Each voice can be used once in a mix.', true);
      return null;
    }
    if (!r.voices.some((v) => v.weight > 0)) {
      say(statusEl, 'Give at least one voice some weight.', true);
      return null;
    }
    return r;
  }

  $('addVoice').addEventListener('click', () => {
    const used = new Set([...mixRows.querySelectorAll('select')].map((s) => s.value));
    addMixRow((usable().find((v) => !used.has(v.id)) || {}).id, 0.5);
  });
  $('ctlGender').addEventListener('input', () => {
    $('ctlGenderOut').textContent = Number($('ctlGender').value).toFixed(2);
  });

  async function busyRun(btn, statusEl, fn) {
    if (busy) return;
    busy = true;
    btn.disabled = true;
    try {
      await fn();
    } catch (e) {
      say(statusEl, e.message, true);
    }
    busy = false;
    btn.disabled = false;
  }

  $('designPreview').addEventListener('click', () => {
    const st = $('designStatus');
    const r = checkMix(st);
    if (!r) return;
    busyRun($('designPreview'), st, async () => {
      say(st, 'Rendering preview (a few seconds)…');
      const res = await call(API + '/design/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ recipe: r, text: $('designText').value }),
      });
      await playBlob($('designAudio'), res);
      say(st, 'Preview ready.');
    });
  });

  $('designSave').addEventListener('click', () => {
    const st = $('designSaveStatus');
    const r = checkMix(st);
    if (!r) return;
    if (!$('designName').value.trim()) {
      say(st, 'Give the voice a name first.', true);
      $('designName').focus();
      return;
    }
    busyRun($('designSave'), st, async () => {
      const rec = await json(API + '/design/save', { recipe: r, name: $('designName').value, kind: 'blend' });
      say(st, 'Saved "' + rec.name + '" to your library' + (editingId ? ' as a new version.' : '.'));
      await loadLibrary();
    });
  });

  function openRecipe(v) {
    const rcp = v.meta.recipe;
    mixRows.replaceChildren();
    rcp.voices.slice(0, 5).forEach((x) => addMixRow(x.id, x.weight));
    while (mixRows.children.length < 2) addMixRow();
    $('ctlGender').value = String((rcp.controls || {}).gender || 0);
    $('ctlGender').dispatchEvent(new Event('input'));
    $('designName').value = v.name;
    editingId = v.id;
    say($('designSaveStatus'), 'Editing "' + v.name + '". Saving keeps the original and adds the new version.');
    showTab($('tab-design'), true);
  }

  // ---------------------------------------------------------------- describe
  const accentSel = $('descAccent');
  for (const [k, name] of Object.entries(LANG_CODES)) accentSel.append(el('option', { value: k, text: name }));

  $('descGo').addEventListener('click', () => {
    const st = $('descStatus');
    const body = {
      prompt: $('descPrompt').value,
      gender: $('descGender').value,
      accent: accentSel.value,
      age: $('descAge').value,
      energy: $('descEnergy').value,
    };
    if (!body.prompt.trim() && !body.gender && !body.accent && !body.age && !body.energy) {
      say(st, 'Describe the voice or pick at least one option.', true);
      return;
    }
    busyRun($('descGo'), st, async () => {
      say(st, 'Picking voices…');
      const out = await json(API + '/describe', body);
      say(
        st,
        (out.understood.length
          ? 'Understood: ' + out.understood.join(', ') + '.'
          : 'No keywords recognised; these are general picks.') + (out.notes.length ? ' ' + out.notes.join(' ') : ''),
      );
      $('descOptions').replaceChildren(...out.options.map((o, i) => optionCard(o, i + 1)));
    });
  });

  function optionCard(o, n) {
    const audioEl = el('audio', { controls: '', hidden: '' });
    const st = el('p', { class: 'status', role: 'status' });
    const play = el('button', { class: 'btn small', type: 'button', text: 'Play option ' + n });
    play.addEventListener('click', () =>
      busyRun(play, st, async () => {
        say(st, 'Rendering…');
        const res = await call(API + '/design/preview', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ recipe: o.recipe, text: $('designText').value }),
        });
        await playBlob(audioEl, res);
        say(st, '');
      }),
    );
    const name = el('input', {
      type: 'text',
      maxlength: '60',
      placeholder: 'Name',
      'aria-label': 'Name for option ' + n,
    });
    const save = el('button', { class: 'btn secondary small', type: 'button', text: 'Save' });
    save.addEventListener('click', () => {
      if (!name.value.trim()) {
        say(st, 'Give the voice a name first.', true);
        name.focus();
        return;
      }
      busyRun(save, st, async () => {
        const rec = await json(API + '/design/save', { recipe: o.recipe, name: name.value, kind: 'describe' });
        say(st, 'Saved "' + rec.name + '".');
        await loadLibrary();
      });
    });
    const tweak = el('button', {
      class: 'btn secondary small',
      type: 'button',
      text: 'Fine-tune in Design',
      onclick: () => openRecipe({ name: name.value || 'Option ' + n, meta: { recipe: o.recipe } }),
    });
    return el(
      'div',
      { class: 'option' },
      el('strong', { text: 'Option ' + n }),
      el('span', { class: 'hint', text: o.summary }),
      el('div', { class: 'row' }, play),
      audioEl,
      el('div', { class: 'row' }, name, save),
      tweak,
      st,
    );
  }

  // ---------------------------------------------------------------- match
  let job = null,
    timer = null;
  const mStatus = $('matchStatus'),
    bar = $('matchBar');

  $('matchGo').addEventListener('click', () => {
    const f = $('matchFile').files[0];
    if (!f) {
      say(mStatus, 'Choose a recording first.', true);
      $('matchFile').focus();
      return;
    }
    if (f.size > 100 * 1024 * 1024) {
      say(mStatus, 'That file is over 100 MB.', true);
      return;
    }
    if (!$('matchConsent').checked) {
      say(mStatus, 'Confirm that you own this voice or have permission to use it.', true);
      $('matchConsent').focus();
      return;
    }
    const fd = new FormData();
    fd.append('file', f);
    fd.append('consent', 'true');
    fd.append('budget', $('matchBudget').value);
    $('matchResult').hidden = true;
    busyRun($('matchGo'), mStatus, async () => {
      say(mStatus, 'Uploading…');
      const out = await call(API + '/match', { method: 'POST', body: fd }).then((r) => r.json());
      job = out.job;
      bar.hidden = false;
      $('matchCancel').hidden = false;
      $('matchGo').disabled = true;
      poll();
    });
  });

  async function poll() {
    clearTimeout(timer);
    try {
      const st = await call(API + '/match/' + job).then((r) => r.json());
      /** @type {HTMLElement} */ (bar.firstElementChild).style.width = Math.round(100 * (st.progress || 0)) + '%';
      if (st.status === 'running') {
        say(
          mStatus,
          st.step +
            (st.similarity != null ? ' · best similarity ' + st.similarity.toFixed(3) : '') +
            ' · ' +
            Math.round(st.elapsed) +
            ' s',
        );
        timer = setTimeout(poll, 1000);
        return;
      }
      endJob();
      if (st.status === 'done') showResult(st.result);
      else if (st.status === 'cancelled') say(mStatus, 'Cancelled. Nothing was saved.');
      else say(mStatus, st.error || 'Matching failed.', true);
    } catch (e) {
      endJob();
      say(mStatus, e.message, true);
    }
  }

  function endJob() {
    $('matchCancel').hidden = true;
    $('matchGo').disabled = false;
    bar.hidden = true;
  }

  $('matchCancel').addEventListener('click', async () => {
    if (!job) return;
    say(mStatus, 'Cancelling…');
    try {
      await call(API + '/match/' + job + '/cancel', { method: 'POST' });
    } catch (e) {
      say(mStatus, e.message, true);
    }
  });

  function showResult(r) {
    say(mStatus, 'Done in ' + Math.round(r.seconds) + ' s: ' + r.tries + ' tries, ' + r.kept + ' kept.');
    $('simBefore').textContent = r.before.toFixed(3);
    $('simAfter').textContent = r.after.toFixed(3);
    $('simStock').replaceChildren(
      ...r.best_stock.map((s) => el('span', { class: 'tag', text: s.id + ' ' + s.similarity.toFixed(2) })),
    );
    const base = API + '/match/' + job + '/audio?which=';
    $('playRef').src = base + 'reference';
    $('playBefore').src = base + 'before';
    $('playAfter').src = base + 'after';
    $('matchResult').hidden = false;
  }

  $('matchSave').addEventListener('click', () => {
    const st = $('matchSaveStatus');
    if (!$('matchName').value.trim()) {
      say(st, 'Give the voice a name first.', true);
      $('matchName').focus();
      return;
    }
    busyRun($('matchSave'), st, async () => {
      const rec = await json(API + '/match/' + job + '/save', { name: $('matchName').value });
      say(st, 'Saved "' + rec.name + '" to your library.');
      await loadLibrary();
    });
  });

  $('goClone').addEventListener('click', () => showTab($('tab-clone'), true));

  // ---------------------------------------------------------------- clone fallback
  window.addEventListener('load', () => {
    if ($('clonePanel').children.length) $('cloneFallback').hidden = true;
  });

  loadLibrary();
})();
