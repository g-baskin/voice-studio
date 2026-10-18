/* Voice cloning panel: renders into #clonePanel. Builds DOM with createElement/textContent only. */
(() => {
  const root = document.getElementById('clonePanel');
  if (!root) return;
  const SCRIPT = 'The morning was quiet, and the coffee was still too hot to drink. I opened the window, listened to ' +
    'the birds, and thought about the long list of things I wanted to finish today. First, a short walk by the river. ' +
    'Then a call with an old friend, and maybe, if the weather holds, dinner outside on the porch.';
  const el = (tag, props = {}, ...kids) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
      if (k === 'class') n.className = v; else if (k === 'text') n.textContent = v;
      else if (k.startsWith('on')) n.addEventListener(k.slice(2), v); else n.setAttribute(k, v);
    }
    kids.flat().forEach(c => c != null && n.append(c));
    return n;
  };
  const style = el('style', { text: `
    #clonePanel .row{display:flex;gap:12px;flex-wrap:wrap;align-items:center;margin:10px 0}
    #clonePanel .field{display:flex;flex-direction:column;gap:4px;margin:12px 0}
    #clonePanel textarea,#clonePanel input[type=text]{width:100%}
    #clonePanel .script{background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:12px;margin:8px 0}
    #clonePanel .timer{font-variant-numeric:tabular-nums;font-weight:700}
    #clonePanel .tabs{display:flex;gap:4px}
    #clonePanel .tabs [aria-selected=true]{box-shadow:inset 0 -2px 0 var(--accent)}
    #clonePanel progress{width:100%}
    #clonePanel audio{width:100%;margin-top:8px}
    #clonePanel .consent{display:flex;gap:8px;align-items:flex-start;font-weight:600}
    #clonePanel .consent input{width:20px;height:20px;margin-top:2px;flex:none}
    #clonePanel .rec{color:var(--bad)}
    #clonePanel .tags{gap:6px;margin:4px 0 8px}
    #clonePanel .tags .btn{padding:6px 10px;font-weight:500;font-size:.9rem}` });
  const api = async (url, opts) => {
    const r = await fetch(url, opts);
    if (!r.ok) {
      let msg = `Request failed (${r.status}).`;
      try { msg = (await r.json()).detail || msg; } catch { /* not json */ }
      throw new Error(typeof msg === 'string' ? msg : 'Invalid input.');
    }
    return r;
  };

  // ---------- status
  const statusCard = el('div', { class: 'card', 'aria-live': 'polite' }, el('h2', { text: 'Clone a voice' }),
    el('p', { class: 'status', text: 'Checking the cloning engine…' }));

  // ---------- create
  let blob = null, blobName = '';
  const fileInput = el('input', { type: 'file', id: 'cloneFile', accept: '.wav,.mp3,.m4a,.mp4,.webm,.ogg,audio/*' });
  const fileInfo = el('p', { class: 'hint', id: 'cloneFileInfo', text: 'WAV, MP3, M4A, MP4, WebM or OGG, 5 to 60 seconds, up to 50 MB.' });
  fileInput.addEventListener('change', () => {
    const f = fileInput.files[0];
    blob = f || null; blobName = f ? f.name : '';
    fileInfo.textContent = f ? `Selected: ${f.name} (${(f.size / 1048576).toFixed(1)} MB)` : 'No file chosen.';
    validate();
  });
  const uploadPane = el('div', { id: 'clonePaneUpload', role: 'tabpanel' },
    el('label', { for: 'cloneFile', text: 'Reference recording' }), el('div', {}, fileInput), fileInfo);

  const timer = el('span', { class: 'timer', 'aria-live': 'off', text: '0:00' });
  const recBtn = el('button', { type: 'button', class: 'btn', text: 'Start recording' });
  const recMsg = el('p', { class: 'status', role: 'status' });
  const recAudio = el('audio', { controls: '', hidden: '' });
  let recorder = null, tick = null, started = 0;
  const fmt = s => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
  recBtn.addEventListener('click', async () => {
    if (recorder && recorder.state === 'recording') { recorder.stop(); return; }
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      recMsg.textContent = 'This browser cannot record audio. Upload a file instead.'; recMsg.className = 'error'; return;
    }
    let stream;
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
    catch { recMsg.textContent = 'Microphone access was blocked. Allow it in the browser, or upload a file.'; recMsg.className = 'error'; return; }
    const chunks = [];
    recorder = new MediaRecorder(stream);
    recorder.ondataavailable = e => e.data.size && chunks.push(e.data);
    recorder.onstop = () => {
      clearInterval(tick); stream.getTracks().forEach(t => t.stop());
      const secs = (Date.now() - started) / 1000;
      const type = recorder.mimeType || 'audio/webm';
      blob = new Blob(chunks, { type }); blobName = 'recording.' + (type.includes('ogg') ? 'ogg' : type.includes('mp4') ? 'm4a' : 'webm');
      recAudio.src = URL.createObjectURL(blob); recAudio.hidden = false;
      recBtn.textContent = 'Record again'; recBtn.classList.remove('danger');
      recMsg.className = secs < 5 ? 'error' : 'status';
      recMsg.textContent = secs < 5 ? `Only ${secs.toFixed(0)} s recorded. Record at least 5 seconds.` : `Recorded ${fmt(secs)}. Listen back, or record again.`;
      if (secs < 5) blob = null;
      validate();
    };
    recorder.start(); started = Date.now(); timer.textContent = '0:00';
    tick = setInterval(() => {
      const s = (Date.now() - started) / 1000; timer.textContent = fmt(s);
      if (s >= 60) recorder.stop();
    }, 250);
    recBtn.textContent = 'Stop recording'; recMsg.className = 'status rec'; recMsg.textContent = 'Recording… read the script above.';
  });
  const recordPane = el('div', { id: 'clonePaneRecord', role: 'tabpanel', hidden: '' },
    el('p', { class: 'hint', text: 'Read this aloud in your normal voice (about 20 seconds), in a quiet room:' }),
    el('p', { class: 'script', text: SCRIPT }),
    el('div', { class: 'row' }, recBtn, el('span', {}, 'Time ', timer, el('span', { class: 'hint', text: ' (5–60 s)' }))),
    recMsg, recAudio);

  const tabs = [['Upload a file', uploadPane], ['Record now', recordPane]].map(([label, pane], i) => {
    const t = el('button', { type: 'button', role: 'tab', class: 'btn secondary', 'aria-selected': String(i === 0),
      'aria-controls': pane.id, text: label });
    t.addEventListener('click', () => select(i));
    t.addEventListener('keydown', e => {
      if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') { const j = (i + 1) % 2; select(j); tabEls[j].focus(); }
    });
    return t;
  });
  const tabEls = tabs;
  const select = i => {
    tabs.forEach((t, j) => { t.setAttribute('aria-selected', String(i === j)); t.tabIndex = i === j ? 0 : -1; });
    uploadPane.hidden = i !== 0; recordPane.hidden = i !== 1;
    blob = null; fileInput.value = ''; recAudio.hidden = true; validate();
  };
  tabs[1].tabIndex = -1;

  const nameIn = el('input', { type: 'text', id: 'cloneName', maxlength: '60', autocomplete: 'off', placeholder: 'e.g. My narration voice' });
  const transIn = el('textarea', { id: 'cloneTranscript', rows: '2', maxlength: '2000', placeholder: 'What is said in the recording (optional)' });
  const consent = el('input', { type: 'checkbox', id: 'cloneConsent' });
  const createBtn = el('button', { type: 'button', class: 'btn', id: 'cloneCreate', text: 'Create voice', disabled: '' });
  const createMsg = el('p', { class: 'status', id: 'cloneCreateMsg', role: 'status' });
  const why = el('p', { class: 'hint', id: 'cloneWhy' });
  function validate() {
    const missing = [];
    if (!blob) missing.push('a recording');
    if (!nameIn.value.trim()) missing.push('a name');
    if (!consent.checked) missing.push('the consent checkbox');
    createBtn.disabled = missing.length > 0 || !engineOk;
    why.textContent = !engineOk ? 'Install the cloning engine first.' : missing.length ? `Still needed: ${missing.join(', ')}.` : 'Ready.';
  }
  [nameIn, consent].forEach(n => n.addEventListener('input', validate));
  consent.addEventListener('change', validate);
  createBtn.addEventListener('click', async () => {
    validate(); if (createBtn.disabled) return;
    const fd = new FormData();
    fd.append('name', nameIn.value.trim()); fd.append('consent', 'true');
    fd.append('transcript', transIn.value.trim()); fd.append('file', blob, blobName || 'reference.wav');
    createBtn.disabled = true; createMsg.className = 'status'; createMsg.textContent = 'Preparing the reference recording…';
    try {
      const rec = await (await api('api/clone/voices', { method: 'POST', body: fd })).json();
      createMsg.textContent = `Created “${rec.name}” from ${rec.meta.reference_seconds} s of audio. Preview it below.`;
      await loadVoices(rec.id); previewText.focus();
    } catch (e) { createMsg.className = 'error'; createMsg.textContent = e.message; }
    validate();
  });
  const createCard = el('div', { class: 'card' }, el('h3', { text: '1. Reference recording' }),
    el('div', { class: 'tabs', role: 'tablist', 'aria-label': 'Reference source' }, tabs), uploadPane, recordPane,
    el('div', { class: 'field' }, el('label', { for: 'cloneName', text: 'Voice name' }), nameIn),
    el('div', { class: 'field' }, el('label', { for: 'cloneTranscript' }, 'Transcript ', el('span', { class: 'hint', text: '(optional)' })), transIn),
    el('label', { class: 'consent', for: 'cloneConsent' }, consent,
      el('span', { text: 'I own this voice or have permission to clone it.' })),
    el('div', { class: 'row' }, createBtn), why, createMsg);

  // ---------- preview
  const voiceSel = el('select', { id: 'cloneVoice' });
  const previewText = el('textarea', { id: 'clonePreviewText', rows: '3', maxlength: '500' });
  previewText.value = 'Hello! This is my cloned voice. How does it sound?';
  const count = el('span', { class: 'hint' });
  const updCount = () => { count.textContent = `${previewText.value.length}/500`; };
  previewText.addEventListener('input', updCount); updCount();
  // emotion tags: one button per supported tag, inserting it at the cursor (filled from /api/clone/status)
  const tagRow = el('div', { class: 'row tags', id: 'cloneTags', role: 'group', 'aria-label': 'Insert an emotion tag', hidden: '' });
  const insertTag = tag => {
    const v = previewText.value, a = previewText.selectionStart ?? v.length, b = previewText.selectionEnd ?? a;
    const before = v.slice(0, a), after = v.slice(b);
    const ins = (before && !/\s$/.test(before) ? ' ' : '') + tag + (after && !/^\s/.test(after) ? ' ' : '');
    if ((before + ins + after).length > 500) { prevMsg.className = 'error'; prevMsg.textContent = 'No room for another tag (500 characters max).'; return; }
    previewText.value = before + ins + after;
    previewText.focus(); previewText.setSelectionRange(a + ins.length, a + ins.length); updCount();
  };
  const setTags = tags => {
    tagRow.replaceChildren(el('span', { class: 'hint', text: 'Insert:' }), ...tags.map(t =>
      el('button', { type: 'button', class: 'btn secondary tag', 'data-tag': t, text: t, onclick: () => insertTag(t) })));
    tagRow.hidden = !tags.length;
  };
  const langSel = el('select', { id: 'cloneLang' }, el('option', { value: 'en', text: 'English' }));
  const langHint = el('p', { class: 'hint', id: 'cloneLangHint', hidden: '',
    text: 'Other languages: a built-in voice reads the text, then it is re-voiced as your clone. Pronunciation and rhythm come from the built-in voice; emotion tags are ignored.' });
  langSel.addEventListener('change', () => { langHint.hidden = langSel.value === 'en'; tagRow.hidden = langSel.value !== 'en' || !tagRow.childElementCount; });
  const prevBtn = el('button', { type: 'button', class: 'btn', id: 'clonePreview', text: 'Preview', disabled: '' });
  const prog = el('progress', { max: '1', value: '0', hidden: '' });
  const prevMsg = el('p', { class: 'status', id: 'clonePreviewMsg', role: 'status' });
  const tagWarn = el('p', { class: 'hint', id: 'cloneTagWarn', role: 'status', hidden: '' });
  const player = el('audio', { controls: '', id: 'clonePlayer', hidden: '' });
  const dl = el('a', { class: 'btn secondary', id: 'cloneDownload', download: 'clone-preview.wav', hidden: '', text: 'Download WAV' });
  prevBtn.addEventListener('click', async () => {
    const text = previewText.value.trim();
    if (!voiceSel.value) { prevMsg.className = 'error'; prevMsg.textContent = 'Create or choose a cloned voice first.'; return; }
    if (!text) { prevMsg.className = 'error'; prevMsg.textContent = 'Type some text to preview.'; previewText.focus(); return; }
    const fd = new FormData(); fd.append('voice', voiceSel.value); fd.append('text', text); fd.append('language', langSel.value);
    prevBtn.disabled = true; prog.hidden = false; prog.value = 0; player.hidden = dl.hidden = true;
    // ~2.5 words per second of speech; warm fp32 renders ~4.5 s per second of speech, +~20 s if the engine is cold
    // other languages go Kokoro -> voice changer (~2.5 s per second of speech)
    const words = text.split(/\s+/).length, est = Math.round((words / 2.5) * (langSel.value === 'en' ? 4.5 : 2.5) + 5 + (warm ? 0 : 20));
    prevMsg.className = 'status';
    prevMsg.textContent = `Rendering… about ${est} s (roughly 4–5 s of compute per second of speech${warm ? '' : ', plus ~20 s to load the engine'}).`;
    const t0 = Date.now();
    try {
      const { job, warning } = await (await api('api/clone/preview', { method: 'POST', body: fd })).json();
      tagWarn.hidden = !warning; tagWarn.textContent = warning || '';
      for (;;) {
        await new Promise(r => setTimeout(r, 1000));
        const s = await (await api(`api/clone/preview/${job}`)).json();
        prog.value = s.progress || 0;
        if (s.status === 'error') throw new Error(s.error);
        if (s.status === 'done') {
          const url = URL.createObjectURL(await (await api(`api/clone/preview/${job}/audio`)).blob());
          player.src = url; dl.href = url; player.hidden = dl.hidden = false;
          prevMsg.textContent = `Done: ${s.seconds} s of speech in ${s.render_seconds} s.`; warm = true;
          break;
        }
        prevMsg.textContent = `${s.step || 'Rendering'}… ${Math.round((Date.now() - t0) / 1000)} s elapsed (estimate ~${est} s).`;
      }
    } catch (e) { prevMsg.className = 'error'; prevMsg.textContent = e.message; }
    prog.hidden = true; prevBtn.disabled = !voiceSel.value || !engineOk;
  });
  const empty = el('p', { class: 'hint', text: 'No cloned voices yet. Create one above.' });
  const previewCard = el('div', { class: 'card' }, el('h3', { text: '2. Preview' }), empty,
    el('div', { class: 'field' }, el('label', { for: 'cloneVoice', text: 'Cloned voice' }), voiceSel),
    el('div', { class: 'field' }, el('label', { for: 'clonePreviewText' }, 'Test text ', count), previewText,
      el('p', { class: 'hint', id: 'cloneTagHint', text: 'Emotion tags like [laugh] or [sigh] add that sound where they sit. Other [bracketed] text is removed.' })),
    tagRow,
    el('div', { class: 'field' }, el('label', { for: 'cloneLang', text: 'Language' }), langSel, langHint),
    el('div', { class: 'row' }, prevBtn, dl), prog, prevMsg, tagWarn, player);

  async function loadVoices(pick) {
    try {
      const { catalog } = await (await api('api/voices')).json();
      const clones = catalog.filter(v => v.kind === 'clone');
      voiceSel.replaceChildren(...clones.map(v => el('option', { value: v.id, text: v.name })));
      const keep = vcVoice.value;
      vcVoice.replaceChildren(...clones.map(v => el('option', { value: v.id, text: v.name })));
      if (pick) voiceSel.value = pick;
      if (keep) vcVoice.value = keep;
      empty.hidden = clones.length > 0;
    } catch (e) { empty.hidden = false; empty.textContent = `Could not load voices: ${e.message}`; }
    prevBtn.disabled = !voiceSel.value || !engineOk;
    vcValidate();
  }

  // ---------- voice changer (speech-to-speech)
  let perf = null, perfName = '';
  const vcFile = el('input', { type: 'file', id: 'vcFile', accept: '.wav,.mp3,.m4a,.mp4,.webm,.ogg,audio/*' });
  const vcOrig = el('audio', { controls: '', id: 'vcOriginal', hidden: '' });
  const vcOrigLabel = el('p', { class: 'hint', text: 'Original', hidden: '' });
  const setPerf = (b, name) => {
    perf = b; perfName = name;
    if (b) { vcOrig.src = URL.createObjectURL(b); }
    vcOrig.hidden = vcOrigLabel.hidden = !b; vcValidate();
  };
  vcFile.addEventListener('change', () => { const f = vcFile.files[0]; setPerf(f || null, f ? f.name : ''); });
  const vcTimer = el('span', { class: 'timer', text: '0:00' });
  const vcRec = el('button', { type: 'button', class: 'btn secondary', id: 'vcRecord', text: 'Record performance' });
  const vcRecMsg = el('p', { class: 'status', role: 'status' });
  let vcRecorder = null, vcTick = null, vcStart = 0;
  vcRec.addEventListener('click', async () => {
    if (vcRecorder && vcRecorder.state === 'recording') { vcRecorder.stop(); return; }
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      vcRecMsg.className = 'error'; vcRecMsg.textContent = 'This browser cannot record audio. Upload a file instead.'; return;
    }
    let stream;
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
    catch { vcRecMsg.className = 'error'; vcRecMsg.textContent = 'Microphone access was blocked. Allow it, or upload a file.'; return; }
    const chunks = [];
    vcRecorder = new MediaRecorder(stream);
    vcRecorder.ondataavailable = e => e.data.size && chunks.push(e.data);
    vcRecorder.onstop = () => {
      clearInterval(vcTick); stream.getTracks().forEach(t => t.stop());
      const secs = (Date.now() - vcStart) / 1000, type = vcRecorder.mimeType || 'audio/webm';
      vcRec.textContent = 'Record again';
      if (secs < 1) { vcRecMsg.className = 'error'; vcRecMsg.textContent = 'Too short. Record at least 1 second.'; setPerf(null, ''); return; }
      vcRecMsg.className = 'status'; vcRecMsg.textContent = `Recorded ${fmt(secs)}.`;
      setPerf(new Blob(chunks, { type }), 'performance.' + (type.includes('ogg') ? 'ogg' : type.includes('mp4') ? 'm4a' : 'webm'));
    };
    vcRecorder.start(); vcStart = Date.now(); vcTimer.textContent = '0:00';
    vcTick = setInterval(() => { const t = (Date.now() - vcStart) / 1000; vcTimer.textContent = fmt(t); if (t >= 60) vcRecorder.stop(); }, 250);
    vcRec.textContent = 'Stop recording'; vcRecMsg.className = 'status rec'; vcRecMsg.textContent = 'Recording… perform your lines.';
  });
  const vcVoice = el('select', { id: 'vcVoice' });
  const vcConsent = el('input', { type: 'checkbox', id: 'vcConsent' });
  const vcBtn = el('button', { type: 'button', class: 'btn', id: 'vcConvert', text: 'Convert', disabled: '' });
  const vcWhy = el('p', { class: 'hint', id: 'vcWhy' });
  const vcProg = el('progress', { max: '1', value: '0', hidden: '' });
  const vcMsg = el('p', { class: 'status', id: 'vcMsg', role: 'status' });
  const vcOut = el('audio', { controls: '', id: 'vcConverted', hidden: '' });
  const vcOutLabel = el('p', { class: 'hint', text: 'Converted', hidden: '' });
  const vcDl = el('a', { class: 'btn secondary', id: 'vcDownload', download: 'voice-changer.wav', hidden: '', text: 'Download WAV' });
  let vcBusy = false;
  function vcValidate() {
    const missing = [];
    if (!perf) missing.push('a performance');
    if (!vcVoice.value) missing.push('a cloned voice');
    if (!vcConsent.checked) missing.push('the rights checkbox');
    vcBtn.disabled = vcBusy || missing.length > 0 || !engineOk;
    vcWhy.textContent = !engineOk ? 'Install the cloning engine first.' : missing.length ? `Still needed: ${missing.join(', ')}.` : 'Ready.';
  }
  vcConsent.addEventListener('change', vcValidate); vcVoice.addEventListener('change', vcValidate);
  vcBtn.addEventListener('click', async () => {
    vcValidate(); if (vcBtn.disabled) return;
    const fd = new FormData();
    fd.append('voice', vcVoice.value); fd.append('consent', 'true'); fd.append('file', perf, perfName || 'performance.wav');
    vcBusy = true; vcValidate(); vcProg.hidden = false; vcProg.value = 0; vcOut.hidden = vcOutLabel.hidden = vcDl.hidden = true;
    const dur = Number.isFinite(vcOrig.duration) ? vcOrig.duration : 10;
    const est = Math.round(dur * 3 + 5 + (warm ? 0 : 20));
    vcMsg.className = 'status'; vcMsg.textContent = `Uploading and converting… about ${est} s.`;
    const t0 = Date.now();
    try {
      const { job } = await (await api('api/clone/convert', { method: 'POST', body: fd })).json();
      for (;;) {
        await new Promise(r => setTimeout(r, 1000));
        const s = await (await api(`api/clone/convert/${job}`)).json();
        vcProg.value = s.progress || 0;
        if (s.status === 'error') throw new Error(s.error);
        if (s.status === 'done') {
          const url = URL.createObjectURL(await (await api(`api/clone/convert/${job}/audio`)).blob());
          vcOut.src = url; vcDl.href = url; vcOut.hidden = vcOutLabel.hidden = vcDl.hidden = false;
          vcMsg.textContent = `Done: ${s.seconds} s converted in ${s.render_seconds} s.`; warm = true;
          break;
        }
        vcMsg.textContent = `${s.step || 'Converting'}… ${Math.round((Date.now() - t0) / 1000)} s elapsed (estimate ~${est} s).`;
      }
    } catch (e) { vcMsg.className = 'error'; vcMsg.textContent = e.message; }
    vcBusy = false; vcProg.hidden = true; vcValidate();
  });
  const vcCard = el('div', { class: 'card' }, el('h3', { text: '3. Voice changer' }),
    el('p', { class: 'hint', text: 'Perform the lines yourself (1–60 s). Your timing, intonation and emotion are kept; the voice becomes the cloned one.' }),
    el('div', { class: 'field' }, el('label', { for: 'vcFile', text: 'Performance recording' }), el('div', {}, vcFile)),
    el('div', { class: 'row' }, vcRec, el('span', {}, 'Time ', vcTimer)), vcRecMsg,
    vcOrigLabel, vcOrig,
    el('div', { class: 'field' }, el('label', { for: 'vcVoice', text: 'Target cloned voice' }), vcVoice),
    el('label', { class: 'consent', for: 'vcConsent' }, vcConsent,
      el('span', { text: 'I have the rights to this performance and permission to use the target voice.' })),
    el('div', { class: 'row' }, vcBtn, vcDl), vcWhy, vcProg, vcMsg, vcOutLabel, vcOut);

  let engineOk = false, warm = false;
  root.replaceChildren(style, statusCard, createCard, previewCard, vcCard);
  validate();
  (async () => {
    const p = statusCard.querySelector('p');
    try {
      const s = await (await api('api/clone/status')).json();
      engineOk = !!s.installed; warm = !!s.warm;
      if (Array.isArray(s.languages)) langSel.replaceChildren(...s.languages.filter(l => l && typeof l.code === 'string')
        .map(l => el('option', { value: l.code, text: String(l.name || l.code) })));
      setTags(Array.isArray(s.emotion_tags) ? s.emotion_tags.filter(t => typeof t === 'string') : []);
      if (engineOk) {
        p.textContent = `Engine: ${s.model} · ${s.license} licence · ${s.sample_rate / 1000} kHz · ${s.device.toUpperCase()}${s.warm ? ' · ready' : ' · loads on first use (~20 s)'}. English only.`;
      } else {
        p.className = 'error'; p.textContent = 'The voice cloning engine is not installed.';
        statusCard.append(el('p', { text: 'In a terminal, in the app folder, run (one time, about 3.3 GB):' }),
          el('pre', { class: 'script' }, el('code', { text: 'scripts/setup_clone_engine.sh' })),
          el('p', { class: 'hint', text: 'Then reload this page.' }));
      }
    } catch (e) { p.className = 'error'; p.textContent = `Could not check the engine: ${e.message}`; }
    validate(); loadVoices();
  })();
})();
