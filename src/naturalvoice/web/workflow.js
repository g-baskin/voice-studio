/* File queue and listening workflow. Requires the template controls in index.html. */
let queue = [], activeIndex = -1, busy = false, stopBatch = false, suggestionKey = null;
let tracks = [], activeTrack = 0, playbackVersion = 0;
const drop = $('#drop'), input = $('#file');
function updateActions() {
  const ready = templatesReady && !!file && !busy;
  for (const id of ['cleanBtn', 'previewBtn', 'suggestBtn']) $('#' + id).disabled = !ready;
  $('#batchBtn').disabled = !templatesReady || busy || !queue.some(item => item.status !== 'done');
  $('#batchDownload').disabled = busy || !queue.some(item => item.job);
  for (const id of ['activeFile', 'clearQueue', 'previewStart', 'previewLength']) $('#' + id).disabled = busy;
  $('#template').disabled = busy || !templatesReady;
  $('#resetTemplate').disabled = busy || !templatesReady;
  $('#saveTemplate').disabled = busy || !templatesReady;
  $('#deleteTemplate').disabled = busy || !savedTemplates[$('#template').value];
  $('#applySuggestion').disabled = busy;
  SLIDERS.forEach(([k]) => { $(`#s-${k}`).disabled = busy || !templatesReady; });
}
function setStatus(text, error = false) {
  $('#cleanStatus').textContent = text; $('#cleanStatus').classList.toggle('error', error);
}
function selectFile(index) {
  activeIndex = index; file = queue[index]?.file || null;
  $('#activeFile').value = String(index); $('#fileName').textContent = file?.name || '';
  suggestionKey = null; $('#suggestion').textContent = ''; $('#applySuggestion').hidden = true;
  updateActions();
}
function renderQueue() {
  $('#queueSection').hidden = queue.length === 0;
  $('#activeFile').replaceChildren(); $('#queueList').replaceChildren();
  queue.forEach((item, i) => {
    const option = document.createElement('option'); option.value = String(i); option.textContent = item.file.name;
    $('#activeFile').append(option);
    const li = document.createElement('li'); li.textContent = `${item.file.name}: ${item.status}${item.error ? ' (' + item.error + ')' : ''}`;
    if (item.result && item.job) {
      const view = document.createElement('button'); view.textContent = 'Compare'; view.disabled = busy;
      view.onclick = () => showResult(item.job, item.result, item.file.name, item.label);
      li.append(view);
      const link = document.createElement('a'); link.textContent = 'Download'; link.href = `api/jobs/${item.job}/result`; link.download = '';
      li.append(link);
    }
    $('#queueList').append(li);
  });
  $('#activeFile').value = String(activeIndex); updateActions();
}
function pickMany(files) {
  if (busy) { setStatus('Wait for the current operation before adding files.', true); return; }
  const incoming = Array.from(files || []);
  const accepted = [], rejected = [];
  for (const f of incoming) {
    if (queue.length + accepted.length >= 20) { rejected.push('Queue limit: 20 files.'); break; }
    if (!/\.(wav|flac|mp3|m4a|aac|ogg|opus|aiff?|mp4|mov|mkv|webm|avi|m4v)$/i.test(f.name)) { rejected.push(f.name + ': unsupported type.'); continue; }
    if (!f.size || f.size > 500 * 1024 * 1024) { rejected.push(f.name + ': empty or larger than 500 MB.'); continue; }
    accepted.push({ file: f, status: 'queued', job: null, result: null });
  }
  if (accepted.length) {
    const index = queue.length; queue.push(...accepted); renderQueue(); selectFile(index);
  }
  setStatus(rejected.join(' '), rejected.length > 0);
}
drop.onclick = () => { if (!busy) input.click(); };
drop.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); drop.onclick(); } };
drop.ondragover = e => { e.preventDefault(); drop.classList.add('over'); };
drop.ondragleave = () => drop.classList.remove('over');
drop.ondrop = e => { e.preventDefault(); drop.classList.remove('over'); pickMany(e.dataTransfer.files); };
input.onchange = () => { pickMany(input.files); input.value = ''; };
window.addEventListener('dragover', e => e.preventDefault());
window.addEventListener('drop', e => e.preventDefault());
$('#activeFile').onchange = () => selectFile(Number($('#activeFile').value));
$('#clearQueue').onclick = () => {
  if (busy) return;
  queue = []; selectFile(-1); renderQueue(); pauseTracks(); $('#result').hidden = true;
  $('#queueStatus').textContent = 'Queue cleared. Previously downloaded files are unchanged.';
};
function snapshot() {
  return { preset: selectedTemplate().preset, controls: currentControls(),
    label: $('#template').selectedOptions[0].textContent + ($('#templateState').textContent.startsWith('Custom') ? ' (custom)' : '') };
}
function section() {
  const start = Number($('#previewStart').value), seconds = Number($('#previewLength').value);
  if (!Number.isFinite(start) || start < 0 || start > 86400 || !Number.isFinite(seconds) || seconds < 10 || seconds > 20)
    throw new Error('Choose a start from 0 to 86400 seconds and a length from 10 to 20 seconds.');
  return { start, seconds };
}
async function responseJSON(response) {
  let data;
  try { data = await response.json(); } catch { throw new Error('The server returned an unreadable response.'); }
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `Request failed (${response.status}).`);
  return data;
}
async function runJob(item, mode, settings, bounds) {
  const fd = new FormData(); fd.append('file', item.file); fd.append('mode', mode); fd.append('preset', settings.preset);
  Object.entries(settings.controls).forEach(([k, v]) => fd.append(k, v));
  fd.append('start', bounds.start); fd.append('seconds', bounds.seconds);
  setStatus(`Uploading ${item.file.name}…`); $('#prog').hidden = false;
  const { job } = await responseJSON(await fetch('api/clean', { method: 'POST', body: fd }));
  // Poll sequentially so slow replies cannot overwrite newer state.
  for (;;) {
    const state = await responseJSON(await fetch(`api/jobs/${job}`));
    $('#prog div').style.width = Math.round((state.progress || 0) * 100) + '%';
    if (state.status === 'error') throw new Error(state.error || 'Processing failed.');
    if (state.status === 'done') return { job, result: state.result };
    setStatus(`${item.file.name}: ${state.step || 'Processing'}…`);
    await new Promise(resolve => setTimeout(resolve, 700));
  }
}
async function runSelected(mode) {
  if (busy || !file || !templatesReady) return;
  const item = queue[activeIndex], settings = snapshot();
  let bounds;
  try { bounds = mode === 'clean' ? {start: 0, seconds: 15} : section(); }
  catch (error) { setStatus(error.message, true); return; }
  busy = true; pauseTracks(); updateActions();
  if (mode === 'clean') { item.status = 'processing'; item.error = null; item.job = null; item.result = null; renderQueue(); }
  try {
    const { job, result } = await runJob(item, mode, settings, bounds);
    if (mode === 'analyze') {
      suggestionKey = result.suggestion.template;
      const option = Array.from($('#template').options).find(o => o.value === suggestionKey);
      $('#suggestion').textContent = `Suggestion: ${option?.textContent || suggestionKey}. ${result.suggestion.reason} Low confidence; based on ${result.seconds}s starting at ${result.start}s. Preview before committing.`;
      $('#applySuggestion').hidden = false;
    } else {
      showResult(job, result, item.file.name, settings.label);
      if (mode === 'clean') Object.assign(item, {job, result, status: 'done', label: settings.label});
    }
    setStatus(mode === 'preview' ? 'Preview ready. Change a template and preview the same section again to compare.' : 'Done.');
  } catch (error) {
    if (mode === 'clean') { item.status = 'error'; item.error = error.message; }
    setStatus(error.message, true);
  } finally { busy = false; $('#prog').hidden = true; renderQueue(); }
}
$('#cleanBtn').onclick = () => runSelected('clean');
$('#previewBtn').onclick = () => runSelected('preview');
$('#suggestBtn').onclick = () => runSelected('analyze');
$('#applySuggestion').onclick = () => {
  if (!suggestionKey || busy) return;
  $('#template').value = suggestionKey; applyTemplate();
};
$('#batchBtn').onclick = async () => {
  if (busy || !templatesReady) return;
  const settings = snapshot(); stopBatch = false; busy = true; pauseTracks(); updateActions();
  $('#stopQueue').hidden = false; $('#stopQueue').disabled = false;
  let completed = 0, failed = 0;
  try {
    for (const item of queue.filter(q => q.status !== 'done')) {
      if (stopBatch) break;
      item.status = 'processing'; item.error = null; item.job = null; item.result = null; renderQueue();
      try {
        const done = await runJob(item, 'clean', settings, {start: 0, seconds: 15});
        Object.assign(item, done, {status: 'done', label: settings.label}); completed++;
        showResult(done.job, done.result, item.file.name, settings.label);
      } catch (error) { item.status = 'error'; item.error = error.message; failed++; }
    }
    $('#queueStatus').textContent = `${completed} completed, ${failed} failed.${stopBatch ? ' Stopped; remaining files stay queued.' : ''} Failed files can be retried with Process queue.`;
    setStatus('Batch finished. Results remain in the queue.');
  } finally { busy = false; $('#stopQueue').hidden = true; $('#prog').hidden = true; renderQueue(); }
};
$('#stopQueue').onclick = () => {
  stopBatch = true; $('#stopQueue').disabled = true;
  $('#queueStatus').textContent = 'Will stop after the current file finishes.';
};
$('#batchDownload').onclick = async () => {
  $('#batchDownload').disabled = true;
  try {
    const r = await fetch('api/batch-download', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({jobs: queue.filter(q => q.job).map(q => q.job)})});
    if (!r.ok) await responseJSON(r);
    const url = URL.createObjectURL(await r.blob());
    const a = document.createElement('a'); a.href = url; a.download = 'natural-voice-batch.zip'; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  } catch (error) { $('#queueStatus').textContent = error.message; }
  finally { updateActions(); }
};

// A/B switches between preloaded, loudness-matched listening copies at the same time position.
function pauseTracks() { playbackVersion++; tracks.forEach(t => t.pause()); $('#abPlay').textContent = 'Play'; }
function clock(value) { return `${Math.floor(value / 60)}:${String(Math.floor(value % 60)).padStart(2, '0')}`; }
function updateTime() {
  const track = tracks[activeTrack]; if (!track) return;
  const duration = Number.isFinite(track.duration) ? track.duration : 0;
  $('#abSeek').max = duration; $('#abSeek').value = track.currentTime;
  $('#abTime').textContent = `${clock(track.currentTime)} / ${clock(duration)}`;
}
async function chooseTrack(index) {
  if (!tracks.length || index === activeTrack) return;
  const previous = tracks[activeTrack], target = tracks[index];
  const time = previous.currentTime, playing = !previous.paused;
  pauseTracks(); const version = playbackVersion;
  activeTrack = index;
  $('#abBefore').setAttribute('aria-pressed', index === 0);
  $('#abAfter').setAttribute('aria-pressed', index === 1);
  try {
    if (target.readyState < 1) {
      await new Promise((resolve, reject) => {
        const timer = setTimeout(() => finish(new Error('Audio took too long to load. Try again.')), 15000);
        const loaded = () => finish(), failed = () => finish(new Error('Comparison audio could not load.'));
        function finish(error) { clearTimeout(timer); target.removeEventListener('loadedmetadata', loaded); target.removeEventListener('error', failed); error ? reject(error) : resolve(); }
        target.addEventListener('loadedmetadata', loaded, {once: true}); target.addEventListener('error', failed, {once: true});
      });
    }
    if (version !== playbackVersion) return;
    target.currentTime = Math.min(time, Number.isFinite(target.duration) ? target.duration : time);
    if (playing) { await target.play(); $('#abPlay').textContent = 'Pause'; }
    $('#abStatus').textContent = index ? 'B: Cleaned' : 'A: Original'; updateTime();
  } catch (error) { $('#abStatus').textContent = error.message; }
}
$('#abBefore').onclick = () => chooseTrack(0); $('#abAfter').onclick = () => chooseTrack(1);
$('#abPlay').onclick = async () => {
  const track = tracks[activeTrack]; if (!track) return;
  try {
    if (track.paused) { await track.play(); $('#abPlay').textContent = 'Pause'; }
    else pauseTracks();
  } catch { $('#abStatus').textContent = 'Playback could not start. Try again after the audio loads.'; }
};
$('#abSeek').oninput = () => {
  const position = Number($('#abSeek').value);
  tracks.forEach(t => { if (t.readyState >= 1) t.currentTime = Math.min(position, t.duration); }); updateTime();
};
function showResult(job, result, name, templateLabel) {
  pauseTracks(); activeTrack = 0;
  tracks = ['compare-before', 'compare-after'].map((which, i) => {
    const track = document.createElement('audio'); track.src = `api/jobs/${job}/${which}`; track.preload = 'auto';
    track.ontimeupdate = updateTime; track.onloadedmetadata = updateTime;
    track.onended = () => { $('#abPlay').textContent = 'Play'; };
    track.onerror = () => { $('#abStatus').textContent = 'Comparison audio unavailable. Try processing again.'; };
    $(i === 0 ? '#beforeMedia' : '#afterMedia').replaceChildren(track); return track;
  });
  $('#abBefore').setAttribute('aria-pressed', 'true'); $('#abAfter').setAttribute('aria-pressed', 'false');
  $('#abStatus').textContent = 'A: Original'; $('#abSeek').value = 0;
  $('#resultTitle').textContent = `${name}: ${result.mode === 'preview' ? 'preview' : 'full-file result'}`;
  $('#resultSettings').textContent = `${templateLabel}. ${result.seconds}s${result.mode === 'preview' ? ' starting at ' + result.start + 's' : ''}.`;
  $('#matchNote').textContent = result.matching.note;
  $('#resultNotes').replaceChildren();
  for (const text of result.warnings) { const p = document.createElement('p'); p.textContent = text; $('#resultNotes').append(p); }
  const b = result.before, a = result.after;
  const rows = [['Listener prediction (1–5)', 'listener', '', 'up'], ['Voice-quality prediction (1–5)', 'voice', '', 'up'],
    ['Pause level (not an echo measurement)', 'echo_db', 'dB', null], ['Detected ringing', 'metallic', 'dB', 'down'],
    ['Brightness / harshness balance', 'harshness_db', 'dB', null]];
  $('#metrics').replaceChildren();
  const header = document.createElement('tr');
  for (const text of ['Measure', 'Before', 'Exported result']) { const cell = document.createElement('th'); cell.textContent = text; header.append(cell); }
  $('#metrics').append(header);
  for (const [label, key, unit, direction] of rows) {
    const row = document.createElement('tr');
    const values = [label, b[key] == null ? 'Unavailable' : `${b[key]} ${unit}`, a[key] == null ? 'Unavailable' : `${a[key]} ${unit}`];
    values.forEach((text, i) => {
      const cell = document.createElement('td'); cell.textContent = text;
      if (i === 2 && direction && b[key] != null && a[key] != null) {
        const delta = (a[key] - b[key]) * (direction === 'up' ? 1 : -1);
        cell.className = delta > 0.1 ? 'good' : delta < -0.1 ? 'worse' : '';
      }
      row.append(cell);
    });
    $('#metrics').append(row);
  }
  const scope = document.createElement('p'); scope.className = 'hint';
  scope.textContent = `DNSMOS predictions use up to the first 60 seconds (${a.score_seconds ?? a.seconds}s scored here). Higher predicted ratings are preferred; less detected ringing may help. Other measures describe changes, not quality verdicts.`;
  $('#resultNotes').append(scope);
  $('#download').href = `api/jobs/${job}/result`;
  $('#download').textContent = result.mode === 'preview' ? 'Download preview audio' : 'Download full natural version';
  $('#result').hidden = false;
}
updateActions();
