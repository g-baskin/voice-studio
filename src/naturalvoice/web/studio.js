// Voice Studio Studio. All user text goes through textContent / value; never innerHTML.
'use strict';
const $ = id => document.getElementById(id);
const DRAFT = 'nv-studio-draft-v1';
const DELIVERY = { neutral: 'Neutral', warm: 'Warm', energetic: 'Energetic', calm: 'Calm', serious: 'Serious', excited: 'Excited', soft: 'Soft' };
let deliveryInfo = {};
let catalog = [];
let state = { title: 'Untitled project', lines: [], dictionary: [], cast: {} };
let projectId = null;
let parsed = null;
let musicId = null;
let job = null;
let captions = [];
const previews = new Map(); // line id -> object URL
let myStyles = [];
let cloneTags = [];
let rewriteStatus = null;

function el(tag, attrs = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'text') n.textContent = v;
    else if (k === 'on') for (const [ev, fn] of Object.entries(v)) n.addEventListener(ev, fn);
    else if (k in n && typeof v !== 'string') n[k] = v;
    else n.setAttribute(k, v);
  }
  for (const c of kids) if (c != null) n.append(c);
  return n;
}
const uid = () => Array.from(crypto.getRandomValues(new Uint8Array(6)), b => b.toString(16).padStart(2, '0')).join('');
const newLine = (voice = 'af_heart', speaker = '', text = '') =>
  ({ id: uid(), text, voice, speaker, speed: 1, pitch: 0, volume: 0, pause: 0.4, delivery: 'neutral', take: 0, takes: [0], target: null, start: null, end: null });
function say(id, msg, bad = false) { const s = $(id); s.textContent = msg; s.classList.toggle('error', bad); }

async function api(path, opts = {}) {
  const r = await fetch('/api/studio' + path, opts);
  if (!r.ok) {
    let msg = `Request failed (${r.status}).`;
    try {
      const j = await r.json();
      if (typeof j.detail === 'string') msg = j.detail;
      else if (Array.isArray(j.detail)) msg = j.detail.map(d => (d.loc || []).slice(1).join(' › ') + ': ' + d.msg).join('; ');
    } catch { /* not JSON */ }
    if (r.status === 429) msg = 'Busy with another render or cleanup. Wait for it to finish, then try again.';
    throw new Error(msg);
  }
  return r;
}
const json = (path, body, method = 'POST') => api(path, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(r => r.json());

// ------------------------------------------------------------------ project payload
function payload() {
  const dictionary = {};
  for (const [w, v] of state.dictionary) if (w.trim() && v.trim()) dictionary[w.trim()] = v.trim();
  return { title: state.title || 'Untitled project', lines: state.lines, dictionary, cast: state.cast, mode: state.mode || 'sequential' };
}
function fromProject(p) {
  state = { title: p.title || 'Untitled project', lines: (p.lines || []).map(l => ({ ...newLine(), ...l })),
            dictionary: Object.entries(p.dictionary || {}), cast: p.cast || {}, mode: p.mode === 'timed' ? 'timed' : 'sequential' };
  $('title').value = state.title;
  $('mode').value = state.mode;
  renderLines(); renderDict();
}
let draftTimer;
function saveDraft() { try { localStorage.setItem(DRAFT, JSON.stringify({ projectId, project: payload() })); } catch { /* storage full or blocked */ } }
let booted = false; // never overwrite a draft with the empty state before boot has restored it
window.addEventListener('pagehide', () => { if (booted) { clearTimeout(draftTimer); saveDraft(); } });
function changed() {
  clearTimeout(draftTimer);
  draftTimer = setTimeout(() => {
    try { localStorage.setItem(DRAFT, JSON.stringify({ projectId, project: payload() })); } catch { /* storage full or blocked */ }
  }, 400);
  $('count').textContent = `${state.lines.length} line${state.lines.length === 1 ? '' : 's'} · ${state.lines.reduce((n, l) => n + l.text.length, 0).toLocaleString()} / 50,000 characters`;
}

// ------------------------------------------------------------------ voices
function voiceSelect(value, label) {
  const s = el('select', { 'aria-label': label });
  const groups = { stock: 'Stock voices', custom: 'My voices (Voice Lab)', clone: 'Cloned voices' };
  // Starred voices are listed first (they also stay in their own group below).
  const starred = catalog.filter(v => v.starred);
  if (starred.length) {
    const g = el('optgroup', { label: '\u2605 Starred' });
    for (const v of starred) g.append(el('option', { value: v.id, text: v.kind === 'stock' ? `${v.name} \u00b7 ${v.gender}, ${v.language}` : v.name }));
    s.append(g);
  }
  for (const [kind, name] of Object.entries(groups)) {
    const vs = catalog.filter(v => (v.kind === 'clone' ? 'clone' : v.kind === 'stock' ? 'stock' : 'custom') === kind);
    if (!vs.length) continue;
    const g = el('optgroup', { label: name });
    for (const v of vs) g.append(el('option', { value: v.id, text: v.kind === 'stock' ? `${v.name} · ${v.gender}, ${v.language}` : v.name }));
    s.append(g);
  }
  if (value && !catalog.some(v => v.id === value)) s.prepend(el('option', { value, text: `${value} (missing)` }));
  s.value = value;
  return s;
}

// ------------------------------------------------------------------ line cards
function numField(label, key, line, min, max, step, unit) {
  const id = `${key}-${line.id}`;
  const out = el('span', { class: 'num' });
  const show = () => { out.textContent = `${line[key] > 0 && key === 'pitch' ? '+' : ''}${line[key]}${unit}`; };
  const inp = el('input', { type: 'range', id, min: String(min), max: String(max), step: String(step), value: String(line[key]) });
  inp.addEventListener('input', () => { line[key] = Number(inp.value); show(); changed(); });
  show();
  return el('div', { class: 'field' }, el('label', { for: id }, label + ' ', out), inp);
}

// ------------------------------------------------------------------ styles, notes, emotion tags, rewrite
function extrasRow(line, i, ta, err) {
  const save = el('button', { type: 'button', class: 'btn secondary small', text: 'Save as my style', 'aria-label': `Save line ${i + 1} settings as a style` });
  save.addEventListener('click', async () => {
    const name = (prompt('Name this style (e.g. "Promo read"):', '') || '').trim();
    if (!name) return;
    try {
      const rec = await json('/styles', { name: name.slice(0, 60), line });
      myStyles.push(rec);
      line.delivery = 'custom'; line.style = { ...rec }; line.speed = 1; line.pitch = 0; line.volume = 0;
      renderLines(line.id, 'select[aria-label$="delivery"]');
      say('proj-status', `Saved style “${rec.name}”. It's in the delivery picker under My styles.`);
    } catch (e) { err.textContent = e.message; }
  });
  const rw = el('button', { type: 'button', class: 'btn secondary small', text: 'Rewrite for speech', 'aria-label': `Rewrite line ${i + 1} for speech` });
  const panel = el('div', { hidden: true });
  rw.addEventListener('click', () => openRewrite(panel, () => line.text, t => { line.text = t; ta.value = t; ta.dispatchEvent(new Event('input')); }, rw));
  return el('div', {}, el('div', { class: 'row', style: 'margin-top:8px' }, save, rw), panel);
}

function noteBox(line, i) {
  const id = `note-${line.id}`;
  const inp = el('input', { type: 'text', id, maxlength: '200', placeholder: 'e.g. warm, slightly amused, slow down at the end', style: 'flex:1 1 16em' });
  inp.value = line.note || '';
  inp.addEventListener('input', () => { line.note = inp.value; changed(); });
  const read = el('div', { class: 'hint', role: 'status', 'aria-live': 'polite' });
  const apply = el('button', { type: 'button', class: 'btn small', text: 'Apply', hidden: true, 'aria-label': `Apply director's note to line ${i + 1}` });
  let pending = null;
  const understand = el('button', { type: 'button', class: 'btn secondary small', text: 'What does this mean?', 'aria-label': `Interpret director's note for line ${i + 1}` });
  understand.addEventListener('click', async () => {
    if (!inp.value.trim()) { read.textContent = 'Write a note first, e.g. “slower, deeper, dramatic pause”.'; return; }
    try {
      pending = await json('/note', { note: inp.value, line });
      const d = pending;
      const nums = `speed ${d.speed}×, pitch ${d.pitch >= 0 ? '+' : ''}${d.pitch} st, volume ${d.volume >= 0 ? '+' : ''}${d.volume} dB, pause after ${d.pause} s, delivery ${DELIVERY[d.delivery] || d.delivery}` + (d.tags.length ? `, adds ${d.tags.map(t => '[' + t + ']').join(' ')}` : '');
      read.replaceChildren(el('strong', { text: 'What I understood: ' }), (d.understood.length ? d.understood.join('; ') : 'nothing I can use') + '. ',
        el('br'), 'Result: ' + nums + '.', ...(d.unused.length ? [el('br'), `Words I couldn't use: ${d.unused.join(', ')}.`] : []));
      apply.hidden = !d.understood.length;
    } catch (e) { read.textContent = e.message; }
  });
  apply.addEventListener('click', () => {
    if (!pending) return;
    Object.assign(line, { speed: pending.speed, pitch: pending.pitch, volume: pending.volume, pause: pending.pause, text: pending.text });
    if (pending.delivery !== line.delivery && pending.delivery !== 'custom') { line.delivery = pending.delivery; line.style = null; }
    renderLines(line.id, `#note-${line.id}`);
    say('proj-status', `Applied the note to line ${i + 1}. You can still adjust every slider.`);
  });
  return el('div', { style: 'margin-top:8px' }, el('label', { for: id, text: "Director's note" }),
    el('div', { class: 'row' }, inp, understand, apply), read);
}

function tagRow(line, i, ta) {
  const box = el('div', { class: 'row', style: 'margin-top:6px' });
  if (!line.voice.startsWith('clone:') || !cloneTags.length) { box.hidden = true; return box; }
  box.append(el('span', { class: 'hint', text: 'Insert emotion:' }));
  for (const t of cloneTags) {
    box.append(el('button', { type: 'button', class: 'btn secondary small', text: `[${t}]`, 'aria-label': `Insert [${t}] into line ${i + 1}`,
      on: { click: () => {
        const a = ta.selectionStart ?? ta.value.length, b = ta.selectionEnd ?? a;
        const pre = ta.value.slice(0, a), ins = (pre && !/\s$/.test(pre) ? ' ' : '') + `[${t}] `;
        ta.value = pre + ins + ta.value.slice(b);
        ta.focus(); ta.selectionStart = ta.selectionEnd = a + ins.length;
        ta.dispatchEvent(new Event('input'));
      } } }));
  }
  return box;
}

function wordDiff(a, b) {
  const A = a.split(/(\s+)/), B = b.split(/(\s+)/);
  if (A.length * B.length > 400000) return [['del', a], ['ins', b]];
  const L = Array.from({ length: A.length + 1 }, () => new Uint16Array(B.length + 1));
  for (let x = A.length - 1; x >= 0; x--) for (let y = B.length - 1; y >= 0; y--)
    L[x][y] = A[x] === B[y] ? L[x + 1][y + 1] + 1 : Math.max(L[x + 1][y], L[x][y + 1]);
  const out = []; let x = 0, y = 0;
  const push = (k, t) => { if (out.length && out[out.length - 1][0] === k) out[out.length - 1][1] += t; else out.push([k, t]); };
  while (x < A.length && y < B.length) {
    if (A[x] === B[y]) { push('same', A[x]); x++; y++; }
    else if (L[x + 1][y] >= L[x][y + 1]) push('del', A[x++]); else push('ins', B[y++]);
  }
  while (x < A.length) push('del', A[x++]);
  while (y < B.length) push('ins', B[y++]);
  return out;
}

function openRewrite(panel, getText, setText, opener) {
  const text = getText();
  panel.hidden = false;
  if (!text.trim()) { panel.replaceChildren(el('p', { class: 'error', text: 'Nothing to rewrite yet.' })); return; }
  const llmOk = rewriteStatus && rewriteStatus.llm && rewriteStatus.llm.available;
  const useLlm = el('input', { type: 'checkbox', disabled: !llmOk });
  const tone = el('select', { 'aria-label': 'Rewrite tone', disabled: !llmOk });
  for (const t of (rewriteStatus && rewriteStatus.tones) || ['natural']) tone.append(el('option', { value: t, text: t }));
  const conv = el('input', { type: 'checkbox' });
  const go = el('button', { type: 'button', class: 'btn small', text: 'Show rewrite' });
  const close = el('button', { type: 'button', class: 'btn secondary small', text: 'Cancel', on: { click: () => { panel.hidden = true; panel.replaceChildren(); opener.focus(); } } });
  const out = el('div', { role: 'status', 'aria-live': 'polite' });
  useLlm.addEventListener('change', () => { tone.disabled = !useLlm.checked; });
  tone.disabled = true;
  go.addEventListener('click', async () => {
    go.disabled = true; out.replaceChildren(el('p', { class: 'hint', text: 'Rewriting…' }));
    try {
      const call = async t => (await fetch('/api/rewrite', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: t, mode: useLlm.checked ? 'llm' : 'rules', tone: tone.value, conversational: conv.checked }) })
        .then(async r => { if (!r.ok) { let m = `Rewrite failed (${r.status}).`; try { const j = await r.json(); if (typeof j.detail === 'string') m = j.detail; } catch {} throw new Error(m); } return r; })).json();
      const tagsOf = t => (t.match(/\[[^\[\]\n]{1,40}\]/g) || []);
      let r = await call(text);
      if (tagsOf(r.text).join('|') !== tagsOf(text).join('|')) {
        // the rewrite changed a [tag]: rewrite only the text between tags, keep every tag exactly
        const parts = text.split(/(\[[^\[\]\n]{1,40}\])/);
        const done = await Promise.all(parts.map((p, k) => (k % 2 || !p.trim()) ? Promise.resolve({ text: p, notes: [] })
          : call(p).then(x => ({ ...x, text: (p.match(/^\s*/)[0]) + x.text.trim() + (p.match(/\s*$/)[0]) }))));
        r = { text: done.map(x => x.text).join(''), engine: r.engine,
              notes: [...new Set(done.flatMap(x => x.notes || []))].concat(['Kept your [tags] exactly as written.']) };
      }
      if (r.text === text) { out.replaceChildren(el('p', { class: 'hint', text: 'No changes suggested: this already reads well aloud.' })); return; }
      const diff = el('p', { class: 'diff wrapword' });
      for (const [k, t] of wordDiff(text, r.text)) {
        if (k === 'same' || !t.trim()) { diff.append(t); continue; }
        const lead = t.match(/^\s*/)[0], tail = t.match(/\s*$/)[0];  // highlight words, not the spaces around them
        diff.append(lead, el(k, { text: t.trim() }), tail);
      }
      const accept = el('button', { type: 'button', class: 'btn small', text: 'Accept rewrite' });
      accept.addEventListener('click', () => { setText(r.text); panel.hidden = true; panel.replaceChildren(); opener.focus(); });
      out.replaceChildren(el('p', { class: 'hint', text: `Before → after (${r.engine || 'rules'}): red is removed, green is added.` }), diff,
        ...(r.notes && r.notes.length ? [el('ul', { class: 'hint' }, ...r.notes.map(n => el('li', { text: n })))] : []),
        el('div', { class: 'row' }, accept, el('button', { type: 'button', class: 'btn secondary small', text: 'Keep original',
          on: { click: () => { panel.hidden = true; panel.replaceChildren(); opener.focus(); } } })));
      accept.focus();
    } catch (e) { out.replaceChildren(el('p', { class: 'error', text: e.message })); }
    finally { go.disabled = false; }
  });
  panel.replaceChildren(el('div', { class: 'rewrite' },
    el('div', { class: 'row' }, el('label', {}, conv, ' Make it conversational'),
      el('label', {}, useLlm, ' Use a language model'), tone, go, close),
    llmOk ? el('p', { class: 'hint', text: `Language model via ${rewriteStatus.llm.via}. [tags] are kept.` })
      : el('p', { class: 'hint', text: 'Built-in rules only. For a language-model rewrite, connect an AI in “Write a script for me” → Connect AI. [tags] are kept.' }),
    out));
  go.focus();
}

function timeField(line, i) {
  const box = el('div', { class: 'row timed-only', style: 'margin-top:6px' });
  box.hidden = state.mode !== 'timed';
  for (const key of ['start', 'end']) {
    const id = `${key}-${line.id}`;
    const inp = el('input', { type: 'number', id, min: '0', max: '86400', step: '0.01', placeholder: key === 'end' ? 'next start' : 'after previous', style: 'width:8em' });
    if (line[key] != null) inp.value = String(line[key]);
    inp.addEventListener('input', () => { const v = Number(inp.value); line[key] = inp.value !== '' && v >= 0 && v <= 86400 ? v : null; changed(); });
    box.append(el('label', { for: id, text: key === 'start' ? 'Starts at (s)' : 'Ends by (s)' }), inp);
  }
  return box;
}
$('mode').addEventListener('change', () => {
  state.mode = $('mode').value;
  document.querySelectorAll('.timed-only').forEach(n => { n.hidden = state.mode !== 'timed'; });
  changed();
});

function lineWarnings(text) {
  const w = [];
  for (const m of text.matchAll(/\[([^\[\]\n]{1,40})\]/g)) {
    const b = m[1].trim();
    const p = b.match(/^pause\s+(\d+(?:\.\d+)?)\s*(s|sec|ms)?$/i);
    if (p) { const s = Number(p[1]) / ((p[2] || '').toLowerCase() === 'ms' ? 1000 : 1); if (s < 0.1 || s > 10) w.push(`[${b}] will be clamped to 0.1–10 s.`); }
    else if (b.toLowerCase() !== 'break') w.push(`[${b}] isn't a known tag, so it will be read aloud.`);
  }
  return w.join(' ');
}

function renderLines(focusId, focusSel) {
  const box = $('lines');
  box.replaceChildren();
  state.lines.forEach((line, i) => box.append(card(line, i)));
  $('empty').hidden = state.lines.length > 0;
  changed();
  if (focusId) {
    const c = box.querySelector(`[data-id="${focusId}"]`);
    (c && (c.querySelector(focusSel || 'textarea') || c)).focus();
  }
}

function move(i, d) {
  const j = i + d;
  if (j < 0 || j >= state.lines.length) return;
  [state.lines[i], state.lines[j]] = [state.lines[j], state.lines[i]];
  return true;
}

function card(line, i) {
  const c = el('article', { class: 'linecard', 'data-id': line.id, 'aria-label': `Line ${i + 1}` });
  const tid = `text-${line.id}`;
  const warn = el('p', { class: 'warn', text: lineWarnings(line.text) });
  const err = el('p', { class: 'err', role: 'alert' });
  const ta = el('textarea', { id: tid, maxlength: '5000', placeholder: 'What this line says…' });
  ta.value = line.text;
  ta.addEventListener('input', () => { line.text = ta.value; warn.textContent = lineWarnings(ta.value); changed(); });

  const spk = el('input', { type: 'text', maxlength: '60', placeholder: 'Speaker', 'aria-label': `Line ${i + 1} speaker`, style: 'width:9em' });
  spk.value = line.speaker;
  spk.addEventListener('input', () => { line.speaker = spk.value; changed(); });
  const vs = voiceSelect(line.voice, `Line ${i + 1} voice`);
  vs.addEventListener('change', () => {
    const wasClone = line.voice.startsWith('clone:');
    line.voice = vs.value; changed();
    if (wasClone !== line.voice.startsWith('clone:')) renderLines(line.id, 'select[aria-label$=" voice"]');
  });
  const ds = el('select', { 'aria-label': `Line ${i + 1} delivery` });
  const gb = el('optgroup', { label: 'Built-in' });
  for (const [k, v] of Object.entries(DELIVERY)) gb.append(el('option', { value: k, text: v, title: deliveryInfo[k] || '' }));
  ds.append(gb);
  const styleDesc = st => `${st.speed}× speed, ${st.pitch >= 0 ? '+' : ''}${st.pitch} st, ${st.gain >= 0 ? '+' : ''}${st.gain} dB, pauses ×${st.pause}, ${st.pause_after} s after` + (st.eq.length ? `, EQ ${st.eq.map(b => `${b[0]} ${b[1]} Hz ${b[2] >= 0 ? '+' : ''}${b[2]} dB`).join(', ')}` : '');
  const inLib = line.delivery === 'custom' && line.style && myStyles.find(m => m.id === line.style.id);
  if (myStyles.length) {
    const gm = el('optgroup', { label: 'My styles' });
    for (const m of myStyles) gm.append(el('option', { value: 'style:' + m.id, text: m.name }));
    ds.append(gm);
  }
  if (line.delivery === 'custom' && line.style && !inLib)
    ds.append(el('optgroup', { label: 'In this project' }, el('option', { value: 'custom', text: `${line.style.name} (saved with project)` })));
  ds.value = line.delivery === 'custom' ? (inLib ? 'style:' + line.style.id : 'custom') : line.delivery;
  const dHint = el('span', { class: 'hint', text: line.delivery === 'custom' && line.style ? styleDesc(line.style) : (deliveryInfo[line.delivery] || '') });
  ds.addEventListener('change', () => {
    if (ds.value.startsWith('style:')) {
      const m = myStyles.find(x => 'style:' + x.id === ds.value);
      // a style is applied by value: delivery recipe + the line's pause; own speed/pitch/volume reset so it sounds as saved
      line.delivery = 'custom'; line.style = { ...m }; line.speed = 1; line.pitch = 0; line.volume = 0; line.pause = m.pause_after;
      renderLines(line.id, 'select[aria-label$="delivery"]'); return;
    }
    if (ds.value !== 'custom') { line.delivery = ds.value; line.style = null; }
    dHint.textContent = line.delivery === 'custom' && line.style ? styleDesc(line.style) : (deliveryInfo[line.delivery] || ''); changed();
  });

  const btn = (text, label, fn, cls = 'btn secondary small') => el('button', { type: 'button', class: cls, text, 'aria-label': label, on: { click: fn } });
  const audio = el('audio', { controls: true, hidden: true, preload: 'none' });
  if (previews.has(line.id)) { audio.src = previews.get(line.id); audio.hidden = false; }
  const prev = btn('▶ Preview', `Preview line ${i + 1}`, () => {});

  // takes: each is a seed for natural variation + a tiny voice-style perturbation
  const takeBox = el('div', { class: 'takes', role: 'radiogroup', 'aria-label': `Line ${i + 1} takes` });
  const playTake = async (t, b) => {
    if (!line.text.trim()) { err.textContent = 'Type something first.'; return; }
    err.textContent = ''; b.disabled = true;
    try {
      const r = await api('/preview', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ line: { ...line, take: t }, dictionary: payload().dictionary, polish: $('polish').checked }) });
      audio.src = URL.createObjectURL(await r.blob()); audio.hidden = false; audio.play().catch(() => {});
    } catch (e) { err.textContent = e.message; } finally { b.disabled = false; }
  };
  const drawTakes = () => {
    takeBox.replaceChildren(el('span', { class: 'hint', text: 'Takes:' }));
    line.takes.forEach((t, n) => {
      const r = el('input', { type: 'radio', name: `take-${line.id}`, checked: line.take === t, 'aria-label': `Use take ${n + 1} for line ${i + 1}` });
      r.addEventListener('change', () => { line.take = t; changed(); });
      const pb = el('button', { type: 'button', class: 'btn secondary small', text: '▶', 'aria-label': `Play take ${n + 1} of line ${i + 1}` });
      pb.addEventListener('click', () => playTake(t, pb));
      takeBox.append(el('label', {}, r, `Take ${n + 1}${t === 0 ? ' (original)' : ''}`), pb);
    });
    const nb = el('button', { type: 'button', class: 'btn secondary small', text: '+ New take', 'aria-label': `New take for line ${i + 1}` });
    nb.disabled = line.takes.length >= 5;
    nb.title = nb.disabled ? 'Five takes max. Pick one and start a new line to keep exploring.' : '';
    nb.addEventListener('click', async () => {
      const t = crypto.getRandomValues(new Uint32Array(1))[0] % 2147483646 + 1;
      line.takes.push(t); changed(); drawTakes();
      const btns = takeBox.querySelectorAll('button[aria-label^="Play take"]');
      await playTake(t, btns[btns.length - 1]);
      takeBox.querySelector('button[aria-label^="New take"]').focus();
    });
    takeBox.append(nb);
  };
  if (!Array.isArray(line.takes) || !line.takes.length) line.takes = [0];
  if (!line.takes.includes(line.take)) line.take = line.takes[0];
  drawTakes();
  const tgtId = `target-${line.id}`;
  const tgt = el('input', { type: 'number', id: tgtId, min: '0.5', max: '600', step: '0.1', placeholder: 'natural', style: 'width:7em' });
  if (line.target) tgt.value = String(line.target);
  tgt.addEventListener('input', () => { const v = Number(tgt.value); line.target = tgt.value && v >= 0.5 && v <= 600 ? v : null; changed(); });
  const tgtField = el('div', { class: 'row', style: 'margin-top:6px' }, el('label', { for: tgtId, text: 'Fit this line to (s)' }), tgt,
    el('span', { class: 'hint', text: 'optional, for dubbing' }));

  c.addEventListener('keydown', e => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); prev.click(); return; }
    if (!e.altKey || (e.key !== 'ArrowUp' && e.key !== 'ArrowDown')) return;
    e.preventDefault();
    if (move(state.lines.indexOf(line), e.key === 'ArrowUp' ? -1 : 1)) renderLines(line.id, e.target.tagName === 'TEXTAREA' ? 'textarea' : null);
  });

  c.append(
    el('header', {},
      el('label', { for: tid, text: `Line ${i + 1}` }),
      el('div', { class: 'row' },
        btn('↑', `Move line ${i + 1} up`, () => { if (move(state.lines.indexOf(line), -1)) renderLines(line.id, '[aria-label^="Move"][aria-label$="up"]'); }),
        btn('↓', `Move line ${i + 1} down`, () => { if (move(state.lines.indexOf(line), 1)) renderLines(line.id, '[aria-label$="down"]'); }),
        btn('Duplicate', `Duplicate line ${i + 1}`, () => { const n = { ...line, id: uid() }; state.lines.splice(state.lines.indexOf(line) + 1, 0, n); renderLines(n.id); }),
        btn('Delete', `Delete line ${i + 1}`, () => { const k = state.lines.indexOf(line); state.lines.splice(k, 1); const nx = state.lines[Math.min(k, state.lines.length - 1)]; renderLines(nx && nx.id); if (!nx) $('add').focus(); }, 'btn danger small'))),
    ta, warn,
    el('div', { class: 'row', style: 'margin:8px 0' }, spk, vs, ds, prev),
    dHint,
    el('div', { class: 'grid', style: 'margin-top:8px' },
      numField('Speed', 'speed', line, 0.5, 2, 0.05, '×'),
      numField('Pitch', 'pitch', line, -4, 4, 0.5, ' st'),
      numField('Volume', 'volume', line, -24, 12, 0.5, ' dB'),
      numField('Pause after', 'pause', line, 0, 10, 0.1, ' s')),
    tgtField, timeField(line, i), extrasRow(line, i, ta, err), noteBox(line, i), tagRow(line, i, ta), takeBox, audio, err);
  prev.addEventListener('click', async () => {
    if (!line.text.trim()) { err.textContent = 'Type something to preview.'; return; }
    err.textContent = ''; prev.disabled = true; prev.textContent = 'Rendering…';
    try {
      const r = await api('/preview', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ line, dictionary: payload().dictionary, polish: $('polish').checked }) });
      const url = URL.createObjectURL(await r.blob());
      if (previews.has(line.id)) URL.revokeObjectURL(previews.get(line.id));
      previews.set(line.id, url);
      audio.src = url; audio.hidden = false; audio.play().catch(() => {});
    } catch (e) { err.textContent = e.message; }
    finally { prev.disabled = false; prev.textContent = '▶ Preview'; }
  });
  return c;
}

$('add').addEventListener('click', () => {
  if (state.lines.length >= 500) { say('render-status', 'A project can have 500 lines at most.', true); return; }
  const last = state.lines[state.lines.length - 1];
  const n = newLine(last ? last.voice : 'af_heart', last ? last.speaker : '');
  state.lines.push(n); renderLines(n.id);
});
$('title').addEventListener('input', () => { state.title = $('title').value; changed(); });

// ------------------------------------------------------------------ dictionary
function renderDict() {
  const box = $('dict');
  box.replaceChildren();
  state.dictionary.forEach((row, i) => {
    const w = el('input', { type: 'text', maxlength: '60', placeholder: 'Word', 'aria-label': `Word ${i + 1}` });
    const v = el('input', { type: 'text', maxlength: '200', placeholder: 'Say it as… or /phonemes/', 'aria-label': `Pronunciation ${i + 1}` });
    w.value = row[0]; v.value = row[1];
    w.addEventListener('input', () => { row[0] = w.value; changed(); });
    v.addEventListener('input', () => { row[1] = v.value; changed(); });
    box.append(el('div', { class: 'dictrow' }, w, v, el('button', { type: 'button', class: 'btn danger small', text: 'Remove',
      'aria-label': `Remove word ${i + 1}`, on: { click: () => { state.dictionary.splice(i, 1); renderDict(); $('dict-add').focus(); } } })));
  });
  if (!state.dictionary.length) box.append(el('p', { class: 'hint', text: 'No words yet.' }));
  $('dict-count').textContent = state.dictionary.length ? `(${state.dictionary.length})` : '';
  changed();
}
$('dict-add').addEventListener('click', () => { state.dictionary.push(['', '']); renderDict(); $('dict').querySelector('.dictrow:last-child input').focus(); });

// ------------------------------------------------------------------ paste import
$('paste-rewrite').addEventListener('click', () => openRewrite($('paste-rw-panel'), () => $('paste').value, t => { $('paste').value = t; }, $('paste-rewrite')));
$('parse').addEventListener('click', async () => {
  const text = $('paste').value;
  if (!text.trim()) { say('paste-status', 'Paste a script first.', true); return; }
  say('paste-status', 'Reading script…');
  try {
    parsed = await json('/parse', { text, cast: state.cast });
    const rows = $('cast-rows');
    rows.replaceChildren();
    for (const c of parsed.cast) {
      const s = voiceSelect(c.voice, `Voice for ${c.speaker || 'untagged lines'}`);
      s.addEventListener('change', () => { c.voice = s.value; });
      rows.append(el('div', { class: 'row', style: 'margin-bottom:8px' }, el('span', { class: 'wrapword', style: 'min-width:8em;font-weight:600', text: c.speaker || '(no speaker)' }), s));
    }
    $('cast').hidden = false;
    say('paste-status', `${parsed.lines.length} lines, ${parsed.cast.length} speaker${parsed.cast.length === 1 ? '' : 's'}.` + (parsed.warnings.length ? ' ' + parsed.warnings.slice(0, 3).join(' ') : ''));
  } catch (e) { say('paste-status', e.message, true); }
});
function importParsed(append) {
  if (!parsed) return;
  const map = Object.fromEntries(parsed.cast.map(c => [c.speaker.toLowerCase(), c.voice]));
  for (const c of parsed.cast) if (c.speaker) state.cast[c.speaker.toLowerCase()] = c.voice;
  const lines = parsed.lines.map(l => ({ ...newLine(), ...l, voice: map[l.speaker.toLowerCase()] || l.voice }));
  if (append && state.lines.length + lines.length > 500) { say('paste-status', 'That would go over 500 lines.', true); return; }
  if (!append && state.lines.some(l => l.text.trim()) && !confirm('Replace the current script with the pasted lines?')) return;
  state.lines = append ? state.lines.concat(lines) : lines;
  renderLines(lines[0] && lines[0].id);
  say('paste-status', `Imported ${lines.length} lines.`);
}
$('import').addEventListener('click', () => importParsed(false));
$('append').addEventListener('click', () => importParsed(true));

// ------------------------------------------------------------------ script writer
const gen = { status: null, speakers: ['Narrator'], result: null, cast: {}, ctrl: null, last: null };
function genSpeakers() {
  const box = $('gen-speakers');
  box.replaceChildren();
  gen.speakers.forEach((n, k) => {
    const inp = el('input', { type: 'text', maxlength: '40', 'aria-label': `Speaker ${k + 1} name`, style: 'width:12em' });
    inp.value = n;
    inp.addEventListener('input', () => { gen.speakers[k] = inp.value; });
    const rm = el('button', { type: 'button', class: 'btn danger small', text: 'Remove', 'aria-label': `Remove speaker ${k + 1}`, disabled: gen.speakers.length < 2,
      on: { click: () => { gen.speakers.splice(k, 1); genSpeakers(); $('gen-add-speaker').focus(); } } });
    box.append(el('div', { class: 'row', style: 'margin-bottom:6px' }, inp, rm));
  });
  $('gen-add-speaker').disabled = gen.speakers.length >= 4;
}
$('gen-add-speaker').addEventListener('click', () => {
  if (gen.speakers.length >= 4) return;
  gen.speakers.push(['Narrator', 'Guest', 'Host', 'Caller'].find(n => !gen.speakers.includes(n)) || `Speaker ${gen.speakers.length + 1}`);
  genSpeakers(); $('gen-speakers').querySelector('.row:last-child input').focus();
});
$('gen-kind').addEventListener('change', () => {
  const blank = gen.speakers.every(n => ['Narrator', 'Host', 'Guest', ''].includes(n.trim()));
  if ($('gen-kind').value === 'dialogue' && gen.speakers.length < 2 && blank) { gen.speakers = ['Host', 'Guest']; genSpeakers(); }
  else if ($('gen-kind').value !== 'dialogue' && blank && gen.speakers.length === 2) { gen.speakers = ['Narrator']; genSpeakers(); }
});
function setSeconds(v) {
  $('gen-seconds').value = String(v);
  for (const b of $('gen-quick').querySelectorAll('button')) b.setAttribute('aria-pressed', String(Number(b.dataset.sec) === Number(v)));
}
$('gen-quick').addEventListener('click', e => { const b = e.target.closest('button[data-sec]'); if (b) setSeconds(b.dataset.sec); });
$('gen-seconds').addEventListener('input', () => setSeconds($('gen-seconds').value));

function genEngineLine() {
  const st_ = gen.status;
  const p = $('gen-engine');
  if (!st_) { p.textContent = "Couldn't reach the script writer. Reload the page to try again."; p.classList.add('error'); return; }
  p.classList.remove('error');
  p.textContent = st_.llm && st_.llm.available ? `Using your language model (via ${st_.llm.via}). Writing can take up to a minute.`
    : 'No AI connected. The built-in outline writer will arrange your points (a template, not an AI). Connect an AI for fully written scripts.';
  drawAi();
}
function drawAi() {
  const L = (gen.status && gen.status.llm) || {};
  const saved = L.available && (L.key_saved || L.env_key);
  $('ai-box').hidden = !!L.available;
  $('ai-connected').hidden = !saved;
  if (saved) {
    $('ai-connected-text').textContent = L.env_key
      ? `Connected: ${L.provider || 'OpenRouter'} (model ${L.model}). The key comes from the OPENROUTER_API_KEY environment variable and can't be removed from here.`
      : `Connected: ${L.provider || 'OpenRouter'} (key ${L.key_hint}, model ${L.model})`;
    $('ai-disconnect').hidden = !!L.env_key;
  }
  $('ai-model').placeholder = L.default_model || 'openai/gpt-4o-mini';
}
function applyLlm(L) {
  gen.status = { ...(gen.status || {}), llm: L };
  if (rewriteStatus) rewriteStatus = { ...rewriteStatus, llm: L };
  genEngineLine();
  $('gen-write').disabled = $('gen-sample').disabled = false;
}
async function llmError(r) {
  let m = '';
  try { const j = await r.json(); m = typeof j.detail === 'string' ? j.detail : ''; } catch { /* not JSON */ }
  return m || `The AI service answered with an error (${r.status}).`;
}
$('ai-form').addEventListener('submit', async e => {
  e.preventDefault();
  const keyEl = $('ai-key');
  const key = keyEl.value.trim();
  if (!key) { say('ai-status', 'Paste your OpenRouter key first.', true); keyEl.focus(); return; }
  const body = { api_key: key };
  if ($('ai-model').value.trim()) body.model = $('ai-model').value.trim();
  $('ai-connect').disabled = true; keyEl.disabled = true;
  say('ai-status', 'Checking the key with a tiny test request… (up to 30 s)');
  try {
    const r = await fetch('/api/llm/key', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    if (!r.ok) throw new Error(await llmError(r));
    const L = await r.json();
    keyEl.value = '';
    applyLlm(L);
    say('ai-status', `Connected via ${L.via}.`);
    say('gen-status', `Connected via ${L.via}. Write script will now use it.`);
  } catch (err) {
    say('ai-status', err.message === 'Failed to fetch' ? "Couldn't reach the app. Is it still running?" : err.message, true);
  } finally { $('ai-connect').disabled = false; keyEl.disabled = false; }
});
$('ai-disconnect').addEventListener('click', async () => {
  if (!confirm('Disconnect the AI and delete the saved key from this computer?')) return;
  $('ai-disconnect').disabled = true;
  try {
    const r = await fetch('/api/llm/key', { method: 'DELETE' });
    if (!r.ok) throw new Error(await llmError(r));
    applyLlm(await r.json());
    say('gen-status', 'Disconnected. The saved key was deleted; the built-in outline writer is used now.');
  } catch (err) { say('gen-status', err.message, true); }
  finally { $('ai-disconnect').disabled = false; }
});
async function genInit() {
  try { gen.status = await (await fetch('/api/scriptgen/status')).json(); } catch { gen.status = null; }
  const st_ = gen.status || { kinds: { ad: 'Ad / commercial' }, tones: ['friendly'] };
  $('gen-kind').replaceChildren(...Object.entries(st_.kinds || {}).map(([k, v]) => el('option', { value: k, text: v })));
  $('gen-tone').replaceChildren(...(st_.tones || []).map(t => el('option', { value: t, text: t[0].toUpperCase() + t.slice(1) })));
  if (st_.min_seconds) { $('gen-seconds').min = st_.min_seconds; $('gen-seconds').max = st_.max_seconds; $('gen-len-hint').textContent = `${st_.min_seconds}–${st_.max_seconds} s`; }
  $('gen-write').disabled = $('gen-sample').disabled = !gen.status;
  genEngineLine(); genSpeakers();
}

function genBusy(on) {
  for (const id of ['gen-write', 'gen-sample', 'gen-again', 'gen-use', 'gen-append']) $(id).disabled = on;
  $('gen-cancel').hidden = !on;
}
async function genRun() {
  const seconds = Number($('gen-seconds').value);
  const speakers = [...new Set(gen.speakers.map(n => n.trim()).filter(Boolean))];
  if (!$('gen-topic').value.trim()) { say('gen-status', 'Say what the script is about first.', true); $('gen-topic').focus(); return; }
  if (!(seconds >= 10 && seconds <= 300)) { say('gen-status', 'Length must be between 10 and 300 seconds.', true); $('gen-seconds').focus(); return; }
  if (!speakers.length) { say('gen-status', 'Name at least one speaker.', true); return; }
  const llm = gen.status && gen.status.llm && gen.status.llm.available;
  const body = { topic: $('gen-topic').value.trim(), brief: $('gen-brief').value, kind: $('gen-kind').value, tone: $('gen-tone').value,
    seconds, speakers, cta: $('gen-cta').value.trim(), audience: $('gen-audience').value.trim(), mode: llm ? 'auto' : 'template',
    emotion_tags: $('gen-tags').checked };
  gen.ctrl = new AbortController();
  genBusy(true);
  say('gen-status', llm ? 'Writing with your language model… (up to a minute)' : 'Arranging your points…');
  const t0 = Date.now();
  const tick = setInterval(() => say('gen-status', `Writing… ${Math.round((Date.now() - t0) / 1000)} s`), 1000);
  try {
    const r = await fetch('/api/scriptgen', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal: gen.ctrl.signal });
    if (!r.ok) {
      let m = '';
      try { const j = await r.json(); m = typeof j.detail === 'string' ? j.detail : Array.isArray(j.detail) ? j.detail.map(d => d.msg).join('; ') : ''; } catch { /* not JSON */ }
      if (r.status === 429) throw new Error('The computer is busy with another job. Wait for it to finish, then try again.');
      if (r.status === 503) throw new Error((m || 'The language model is not available.') + ' Try again, or reload to use the built-in outline writer.');
      throw new Error(m || `The script writer failed (${r.status}).`);
    }
    gen.result = await r.json();
    gen.last = body;
    showGen();
    say('gen-status', `Wrote ${gen.result.lines.length} lines in ${Math.max(1, Math.round((Date.now() - t0) / 1000))} s. Check them, then choose Use this script or Add to end.`);
  } catch (e) {
    if (e.name === 'AbortError') say('gen-status', 'Stopped. Nothing was changed.');
    else say('gen-status', e.message === 'Failed to fetch' ? "Couldn't reach the app. Is it still running?" : e.message, true);
  } finally { clearInterval(tick); gen.ctrl = null; genBusy(false); }
}
$('gen-write').addEventListener('click', genRun);
$('gen-again').addEventListener('click', genRun);
$('gen-cancel').addEventListener('click', () => { if (gen.ctrl) gen.ctrl.abort(); });
$('gen-sample').addEventListener('click', async () => {
  try {
    const r = await fetch('/api/scriptgen/sample?kind=' + encodeURIComponent($('gen-kind').value));
    if (!r.ok) throw new Error('No sample for this type.');
    const s_ = await r.json();
    $('gen-topic').value = s_.topic || ''; $('gen-brief').value = (s_.brief || '').split(/\s*;\s*/).join('\n'); $('gen-cta').value = s_.cta || '';
    if (s_.kind === 'dialogue' && gen.speakers.length < 2) { gen.speakers = ['Host', 'Guest']; genSpeakers(); }
    await genRun();
  } catch (e) { say('gen-status', e.message, true); }
});

function pickVoices(names) {
  const stock = catalog.filter(v => v.kind === 'stock' && /^[ab]/.test(v.id));
  const order = [...catalog.filter(v => v.starred), ...stock.filter(v => !v.starred)];
  // alternate genders so speakers are easy to tell apart
  const f = order.filter(v => v.gender === 'female'), m = order.filter(v => v.gender !== 'female');
  const mixed = [];
  for (let k = 0; k < Math.max(f.length, m.length); k++) { if (f[k]) mixed.push(f[k]); if (m[k]) mixed.push(m[k]); }
  const used = new Set();
  const out = {};
  for (const n of names) {
    const known = state.cast[n.toLowerCase()];
    const v = (known && catalog.some(c => c.id === known) && known) || (mixed.find(c => !used.has(c.id)) || mixed[0] || { id: 'af_heart' }).id;
    used.add(v); out[n] = v;
  }
  return out;
}
function showGen() {
  const R = gen.result;
  $('gen-result').hidden = false;
  $('gen-title').textContent = R.title || 'Untitled script';
  $('gen-badge').textContent = R.engine === 'language model' ? 'Written by your language model' : 'Built-in outline (template)';
  const target = gen.last ? gen.last.seconds : null;
  $('gen-length').textContent = `About ${R.estimated_seconds} s spoken (${R.words} words)` + (target ? `, target ${target} s` : '') + '.';
  $('gen-notes').replaceChildren(...(R.notes || []).map(n => el('li', { text: n })));
  const names = [...new Set(R.lines.map(l => l.speaker))];
  const prev = gen.cast;
  gen.cast = pickVoices(names);
  for (const n of names) if (prev[n]) gen.cast[n] = prev[n];
  drawGenLines(); drawGenCast();
}
function drawGenLines() {
  const box = $('gen-lines');
  box.replaceChildren();
  gen.result.lines.forEach((l, k) => {
    const sp = el('input', { type: 'text', maxlength: '40', 'aria-label': `Script line ${k + 1} speaker` });
    sp.value = l.speaker;
    sp.addEventListener('change', () => { l.speaker = sp.value.trim() || 'Narrator'; if (!gen.cast[l.speaker]) gen.cast[l.speaker] = pickVoices([l.speaker])[l.speaker]; drawGenCast(); });
    const tx = el('textarea', { maxlength: '5000', 'aria-label': `Script line ${k + 1} text`, rows: '2' });
    tx.value = l.text;
    tx.addEventListener('input', () => { l.text = tx.value; });
    const rm = el('button', { type: 'button', class: 'btn danger small', text: 'Remove', 'aria-label': `Remove script line ${k + 1}`,
      on: { click: () => { gen.result.lines.splice(k, 1); drawGenLines(); drawGenCast(); } } });
    box.append(el('div', { class: 'genline' }, sp, tx, rm));
  });
  if (!gen.result.lines.length) box.append(el('p', { class: 'hint', text: 'All lines removed. Write another version, or Cancel.' }));
}
function drawGenCast() {
  const names = [...new Set(gen.result.lines.map(l => l.speaker))];
  $('gen-cast').replaceChildren(...names.map(n => {
    const s_ = voiceSelect(gen.cast[n] || 'af_heart', `Voice for ${n}`);
    s_.addEventListener('change', () => { gen.cast[n] = s_.value; });
    return el('div', { class: 'row', style: 'margin-bottom:6px' }, el('span', { class: 'wrapword', style: 'min-width:8em;font-weight:600', text: n }), s_);
  }));
}
function genInsert(append) {
  const R = gen.result;
  const rows = (R ? R.lines : []).filter(l => l.text.trim());
  if (!rows.length) { say('gen-status', 'There are no lines to add.', true); return; }
  if (append && state.lines.length + rows.length > 500) { say('gen-status', 'That would go over 500 lines.', true); return; }
  if (!append && state.lines.some(l => l.text.trim()) && !confirm(`Replace your current ${state.lines.length} line(s) with this script?`)) return;
  const lines = rows.map(l => newLine(gen.cast[l.speaker] || 'af_heart', l.speaker, l.text.slice(0, 5000)));
  for (const [n, v] of Object.entries(gen.cast)) state.cast[n.toLowerCase()] = v;
  if (!append) { state.lines = lines; if (R.title && (!state.title || state.title === 'Untitled project')) { state.title = R.title.slice(0, 120); $('title').value = state.title; } }
  else state.lines = state.lines.concat(lines);
  renderLines(lines[0].id);
  $('gen-result').hidden = true; gen.result = null;
  say('gen-status', `${append ? 'Added' : 'Inserted'} ${lines.length} lines into the script below.`);
}
$('gen-use').addEventListener('click', () => genInsert(false));
$('gen-append').addEventListener('click', () => genInsert(true));
$('gen-close').addEventListener('click', () => { $('gen-result').hidden = true; gen.result = null; say('gen-status', 'Discarded. Your script is unchanged.'); $('gen-write').focus(); });

// ------------------------------------------------------------------ projects
async function refreshProjects(select) {
  try {
    const { projects } = await (await api('/projects')).json();
    const s = $('projects');
    s.replaceChildren(el('option', { value: '', text: projects.length ? 'Choose a project…' : 'No saved projects yet' }));
    for (const p of projects) s.append(el('option', { value: p.id, text: `${p.title} · ${p.lines} lines` + (p.updated ? ` · ${new Date(p.updated * 1000).toLocaleString()}` : '') }));
    s.value = select || projectId || '';
  } catch (e) { say('proj-status', 'Could not list projects: ' + e.message, true); }
}
$('save').addEventListener('click', async () => {
  say('proj-status', 'Saving…');
  try {
    const rec = projectId ? await json(`/projects/${projectId}`, payload(), 'PUT') : await json('/projects', payload());
    projectId = rec.id; changed();
    await refreshProjects(projectId);
    say('proj-status', `Saved “${rec.project.title}” at ${new Date().toLocaleTimeString()}.`);
  } catch (e) { say('proj-status', 'Not saved: ' + e.message, true); }
});
$('load').addEventListener('click', async () => {
  const id = $('projects').value;
  if (!id) { say('proj-status', 'Choose a project to open.', true); return; }
  try {
    const rec = await (await api(`/projects/${id}`)).json();
    projectId = rec.id; fromProject(rec.project);
    say('proj-status', `Opened “${rec.project.title}”.`);
  } catch (e) { say('proj-status', e.message, true); }
});
$('dup').addEventListener('click', async () => {
  const id = $('projects').value || projectId;
  if (!id) { say('proj-status', 'Save or choose a project to duplicate.', true); return; }
  try {
    const rec = await json(`/projects/${id}/duplicate`, {});
    projectId = rec.id; fromProject(rec.project); await refreshProjects(rec.id);
    say('proj-status', `Made a copy: “${rec.project.title}”.`);
  } catch (e) { say('proj-status', e.message, true); }
});
$('del').addEventListener('click', async () => {
  const id = $('projects').value;
  if (!id) { say('proj-status', 'Choose a saved project to delete.', true); return; }
  const name = $('projects').selectedOptions[0].textContent;
  if (!confirm(`Delete “${name}”? This can't be undone.`)) return;
  try {
    await api(`/projects/${id}`, { method: 'DELETE' });
    if (projectId === id) projectId = null;
    await refreshProjects(); changed();
    say('proj-status', 'Project deleted. The script on screen is still here; save it to keep it.');
  } catch (e) { say('proj-status', e.message, true); }
});
$('newp').addEventListener('click', () => {
  if (state.lines.some(l => l.text.trim()) && !confirm('Start a new project? Unsaved changes on screen will be lost.')) return;
  projectId = null;
  fromProject({ title: 'Untitled project', lines: [newLine()] });
  say('proj-status', 'New project.');
});

// ------------------------------------------------------------------ music
function rangeLabel(id, unit) { const f = () => { $(id + '-v').textContent = $(id).value + unit; }; $(id).addEventListener('input', f); f(); }
rangeLabel('mlevel', ' dB'); rangeLabel('duckdb', ' dB');
$('music').addEventListener('change', async () => {
  const f = $('music').files[0];
  if (!f) return;
  if (f.size > 200 * 1024 * 1024) { $('music-name').textContent = 'too large (200 MB max)'; $('music').value = ''; return; }
  $('music-name').textContent = 'uploading…';
  const fd = new FormData(); fd.append('file', f);
  try {
    const r = await (await api('/music', { method: 'POST', body: fd })).json();
    musicId = r.music_id;
    $('music-name').textContent = `${r.name} (${r.seconds} s)`;
    $('music-clear').hidden = false;
  } catch (e) { musicId = null; $('music-name').textContent = e.message; $('music').value = ''; }
});
$('music-clear').addEventListener('click', () => { musicId = null; $('music').value = ''; $('music-name').textContent = 'none'; $('music-clear').hidden = true; $('music').focus(); });

// ------------------------------------------------------------------ subtitles & video
$('subs').addEventListener('change', async () => {
  const f = $('subs').files[0];
  if (!f) return;
  if (f.size > 2 * 1024 * 1024) { say('paste-status', 'Subtitle file too large (2 MB max).', true); $('subs').value = ''; return; }
  if (state.lines.some(l => l.text.trim()) && !confirm('Replace the current script with the subtitle cues?')) { $('subs').value = ''; return; }
  const fd = new FormData(); fd.append('file', f);
  say('paste-status', 'Reading subtitles…');
  try {
    const r = await (await api('/subtitles?voice=' + encodeURIComponent((state.lines[0] || {}).voice || 'af_heart'), { method: 'POST', body: fd })).json();
    state.lines = r.lines.map(l => ({ ...newLine(), ...l }));
    state.mode = 'timed'; $('mode').value = 'timed';
    renderLines(state.lines[0].id);
    say('paste-status', `Imported ${r.lines.length} timed lines; placement set to Timed.` + (r.warnings.length ? ' ' + r.warnings.slice(0, 3).join(' ') : ''));
  } catch (e) { say('paste-status', e.message, true); }
  $('subs').value = '';
});
let videoId = null;
rangeLabel('vlevel', ' dB');
$('video').addEventListener('change', async () => {
  const f = $('video').files[0];
  if (!f) return;
  if (f.size > 2 * 1024 ** 3) { $('video-name').textContent = 'too large (2 GB max)'; $('video').value = ''; return; }
  $('video-name').textContent = 'uploading…';
  const fd = new FormData(); fd.append('file', f);
  try {
    const r = await (await api('/video', { method: 'POST', body: fd })).json();
    videoId = r.video_id;
    $('video-name').textContent = `${r.name} (${r.seconds} s${r.has_audio ? '' : ', no audio'})`;
    $('video-clear').hidden = false;
  } catch (e) { videoId = null; $('video-name').textContent = e.message; $('video').value = ''; }
});
$('video-clear').addEventListener('click', () => { videoId = null; $('video').value = ''; $('video-name').textContent = 'none'; $('video-clear').hidden = true; $('video').focus(); });

// ------------------------------------------------------------------ render
function fitSeconds() {
  const v = $('fit').value;
  if (!v) return null;
  return v === 'custom' ? Math.min(3600, Math.max(1, Number($('fit-custom').value) || 30)) : Number(v);
}
$('fit').addEventListener('change', () => { $('fit-custom-f').hidden = $('fit').value !== 'custom'; });
function syncTarget() {
  const acx = $('target').value === 'acx';
  $('roomtone').checked = acx;
  if (acx) { $('rate').value = '44100'; $('format').value = 'mp3'; }
}
$('target').addEventListener('change', syncTarget);
document.addEventListener('keydown', e => {
  if (!(e.metaKey || e.ctrlKey)) return;
  if (e.key.toLowerCase() === 's' && !e.shiftKey) { e.preventDefault(); $('save').click(); }
  else if (e.key === 'Enter' && e.shiftKey) { e.preventDefault(); if (!$('render').disabled) $('render').click(); }
});
const fmtDb = v => (v == null ? '—' : v.toFixed(1));
$('render').addEventListener('click', async () => {
  if (!state.lines.some(l => l.text.trim())) { say('render-status', 'Add at least one line with text first.', true); return; }
  const num = (id, lo, hi) => Math.min(hi, Math.max(lo, Number($(id).value) || 0));
  const body = { project: payload(), target: $('target').value, sample_rate: Number($('rate').value), format: $('format').value,
    stems: $('stems').checked, line_clips: $('clips').checked, captions: $('captions').checked, polish: $('polish').checked,
    stop_on_error: $('stoperr').checked, music_id: musicId, music_level_db: Number($('mlevel').value), music_loop: $('loop').checked,
    duck: $('duck').checked, duck_db: Number($('duckdb').value), attack_ms: num('attack', 5, 1000), release_ms: num('release', 20, 3000),
    fade_in: num('fadein', 0, 10), fade_out: num('fadeout', 0, 10), room_tone: $('roomtone').checked,
    target_duration: state.mode === 'timed' ? null : fitSeconds(), video_id: videoId, video_mode: $('vmode').value,
    video_level_db: Number($('vlevel').value), video_subs: $('vsubs').checked };
  $('render').disabled = true;
  say('render-status', 'Starting render…');
  try {
    job = (await json('/render', body)).job;
    $('cancel').hidden = false; $('bar').hidden = false;
    poll(job);
  } catch (e) { $('render').disabled = false; say('render-status', e.message, true); }
});
$('cancel').addEventListener('click', async () => {
  if (!job) return;
  try { await json(`/render/${job}/cancel`, {}); say('render-status', 'Cancelling after the current line…'); } catch (e) { say('render-status', e.message, true); }
});
async function poll(id) {
  let s;
  try { s = await (await api(`/render/${id}`)).json(); } catch (e) { say('render-status', e.message, true); finish(); return; }
  $('bar').firstElementChild.style.width = Math.round(s.progress * 100) + '%';
  if (s.status === 'running') { say('render-status', `${s.step} · ${Math.round(s.progress * 100)}%`); setTimeout(() => poll(id), 500); return; }
  finish();
  if (s.status === 'done') { say('render-status', `Rendered ${s.result.duration} s of audio in ${s.result.elapsed} s.`); showResult(id, s.result); }
  else if (s.status === 'cancelled') say('render-status', 'Render cancelled. Nothing was kept.');
  else say('render-status', s.error || 'The render failed.', true);
  refreshRecent();
}
function finish() { $('render').disabled = false; $('cancel').hidden = true; $('bar').hidden = true; }
const fileUrl = (id, name) => `/api/studio/render/${id}/file/${encodeURIComponent(name)}`;
function showResult(id, res) {
  $('result').hidden = false;
  const mix = res.files.find(f => f.kind === 'mix');
  $('player').src = fileUrl(id, mix.name);
  captions = res.captions || [];
  $('caption').textContent = captions.length ? 'Press play to see captions.' : '';
  const L = res.loudness, m = L.measured;
  const loud = $('loud');
  loud.replaceChildren(el('strong', { class: L.met ? 'ok' : 'bad', text: L.met ? '✓ Target met. ' : '✗ Target not met. ' }),
    `${L.target}: ${fmtDb(m.lufs)} LUFS integrated, ${fmtDb(m.true_peak_db)} dBTP true peak, ${fmtDb(m.rms_db)} dB RMS, noise floor ${m.noise_floor_db == null || m.noise_floor_db < -150 ? 'digital silence' : fmtDb(m.noise_floor_db) + ' dB'}. `,
    el('span', { class: 'hint', text: L.note }));
  const fr = $('fitres'), F = res.fit;
  fr.hidden = !F && !(res.line_fits || []).length;
  const fitBits = [];
  if (F) fitBits.push(`Fit to time: ${F.achieved} s of ${F.target} s target (${F.met ? 'met' : 'NOT met'}); speech ${F.speed_factor}× speed, ${F.stretch}× stretch, pauses ${F.pause_change >= 0 ? '+' : ''}${F.pause_change} s.`, ...F.warnings);
  for (const lf of res.line_fits || []) fitBits.push(`Line ${lf.line}: ${lf.achieved} s of ${lf.target} s.` + (lf.warning ? ' ' + lf.warning : ''));
  fr.replaceChildren(el('strong', { class: F && !F.met ? 'bad' : 'ok', text: F ? (F.met ? '✓ ' : '✗ ') : '' }), fitBits.join(' '));
  const vf = res.files.find(f => f.kind === 'video');
  $('vplayer').hidden = !vf;
  if (vf) $('vplayer').src = fileUrl(id, vf.name); else $('vplayer').removeAttribute('src');
  $('overlaps').replaceChildren(...(res.overlaps || []).map(o => el('li', { class: 'error', text: o.message })));
  const errs = $('errors');
  errs.replaceChildren(...res.errors.map(e => el('li', { class: 'error', text: `Line ${e.line} was skipped: ${e.error}` })),
    ...res.warnings.slice(0, 10).map(w => el('li', { class: 'hint', text: w })));
  const labels = { video: 'Dubbed video', mix: 'Full mix', stem: 'Stem', line: 'Line clip', captions: 'Captions', timeline: 'Timeline (JSON)' };
  $('files').replaceChildren(
    el('li', {}, el('strong', { text: 'Everything (ZIP)' }), el('a', { class: 'btn small', href: fileUrl(id, res.zip), download: res.zip, text: 'Download ZIP' })),
    ...res.files.map(f => el('li', {}, el('span', { class: 'wrapword', text: `${labels[f.kind]}${f.speaker ? ' · ' + f.speaker : ''}: ${f.name}` }),
      el('a', { class: 'btn secondary small', href: fileUrl(id, f.name), download: f.name, text: 'Download', 'aria-label': `Download ${f.name}` }))));
}
$('player').addEventListener('timeupdate', () => {
  const t = $('player').currentTime;
  const c = captions.find(x => t >= x.start && t <= x.end);
  $('caption').textContent = c ? c.text : '';
});
async function refreshRecent() {
  try {
    const { renders } = await (await api('/renders')).json();
    const ul = $('recent');
    if (!renders.length) { ul.replaceChildren(el('li', { class: 'hint', text: 'None yet.' })); return; }
    ul.replaceChildren(...renders.map(r => {
      const li = el('li', {}, el('span', { class: 'wrapword', text: `${r.title} · ${new Date(r.created * 1000).toLocaleTimeString()} · ${r.status}${r.duration ? ` · ${r.duration} s` : ''}` }));
      if (r.status === 'done') li.append(el('button', { type: 'button', class: 'btn secondary small', text: 'Show', 'aria-label': `Show render ${r.title}`,
        on: { click: async () => { const s = await (await api(`/render/${r.job}`)).json(); job = r.job; showResult(r.job, s.result); $('player').focus(); } } }));
      return li;
    }));
  } catch { /* list is a convenience */ }
}

// ------------------------------------------------------------------ boot
(async function boot() {
  try {
    const p = await (await api('/presets')).json();
    for (const [k, v] of Object.entries(p.delivery)) deliveryInfo[k] = v.does;
  } catch { /* labels fall back to names */ }
  const side = await Promise.allSettled([api('/styles').then(r => r.json()), fetch('/api/clone/status').then(r => r.ok ? r.json() : {}),
    fetch('/api/rewrite/status').then(r => r.ok ? r.json() : null)]);
  if (side[0].status === 'fulfilled') myStyles = side[0].value.styles || [];
  if (side[1].status === 'fulfilled' && Array.isArray(side[1].value.emotion_tags))
    cloneTags = side[1].value.emotion_tags.map(t => String(t).replace(/^\[|\]$/g, '')).filter(t => /^[a-z][a-z _-]{0,30}$/i.test(t));
  if (side[2].status === 'fulfilled') rewriteStatus = side[2].value;
  try {
    const r = await fetch('/api/voices');
    if (!r.ok) throw new Error((await r.json()).detail || 'Voices unavailable.');
    catalog = (await r.json()).catalog;
  } catch (e) { say('render-status', 'Voice list unavailable: ' + e.message, true); catalog = [{ id: 'af_heart', name: 'Heart', kind: 'stock', gender: 'female', language: 'American English' }]; }
  let draft = null;
  try { draft = JSON.parse(localStorage.getItem(DRAFT) || 'null'); } catch { /* corrupt draft */ }
  if (draft && draft.project && Array.isArray(draft.project.lines)) {
    projectId = /^[0-9a-f]{12}$/.test(draft.projectId || '') ? draft.projectId : null;
    fromProject(draft.project);
    say('proj-status', 'Restored your unsaved draft from this browser.');
  } else {
    fromProject({ title: 'Untitled project', lines: [newLine('af_heart', 'Narrator', 'Welcome to Voice Studio Studio. [pause 0.5s] Write your script, then press Render.')] });
  }
  const want = new URLSearchParams(location.search).get('voice');
  if (want && /^[a-z0-9_:]{3,40}$/.test(want) && catalog.some(v => v.id === want)) {
    let target = state.lines.find(l => !l.text.trim());
    if (!target) { target = newLine(want); state.lines.push(target); }
    target.voice = want;
    renderLines(target.id);
    const v = catalog.find(x => x.id === want);
    say('proj-status', `Voice “${v.name}” from the Voice Lab is on line ${state.lines.indexOf(target) + 1}.`);
    history.replaceState(null, '', location.pathname);
  }
  await genInit();
  booted = true;
  refreshProjects(); refreshRecent();
})();
