// @ts-check
/** @typedef {import('../../../types/dom').SampleElements} Elements */
/** @typedef {{id:string,name:string,active?:string}} Person */
/** @typedef {{start:number,end:number,speaker:number,overlap:boolean}} Turn */
/** @typedef {{id:string,name:string,status:string,step:string,error?:string,duration?:number,segments?:Turn[],separate:boolean,start:number}} Source */
/** @typedef {{id:string,seconds:number,source_name:string,start:number,end:number,clipped:boolean,rms_db:number,cleaned:boolean}} Sample */
/** @typedef {{id:string,name:string,meta:{reference_version:number,seconds:number}}} Version */

/** @template {keyof Elements} K @param {K} id @returns {Elements[K]} */
function el(id) {
  return /** @type {Elements[K]} */ (document.getElementById(id));
}

/** @param {string} path @param {RequestInit} [init] */
async function api(path, init) {
  const response = await fetch(path, init);
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Check the form values and retry.');
  return data;
}
/** @param {string} path @param {object} body */
function post(path, body) {
  return api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
}
/** @param {string} message @param {boolean} [error] */
function showStatus(message, error = false) {
  el('status').textContent = message;
  el('status').classList.toggle('error', error);
}
/** @param {HTMLButtonElement | null} button @param {() => Promise<void>} action */
async function run(button, action) {
  if (button) button.disabled = true;
  try {
    await action();
  } catch (error) {
    showStatus(
      error instanceof Error ? error.message : 'The operation failed. Retry when the local server is available.',
      true,
    );
  } finally {
    if (button) button.disabled = false;
    updateSelection();
  }
}
/** @param {HTMLSelectElement} select @param {{id:string,name:string}[]} rows @param {string} empty */
function options(select, rows, empty) {
  const previous = select.value;
  select.replaceChildren(new Option(empty, ''));
  rows.forEach((row) => select.add(new Option(row.name, row.id)));
  if (rows.some((row) => row.id === previous)) select.value = previous;
}
/** @param {string} label @param {() => Promise<void>} action */
function button(label, action) {
  const item = document.createElement('button');
  item.type = 'button';
  item.className = 'btn secondary';
  item.textContent = label;
  item.addEventListener('click', () => void run(item, action));
  return item;
}
/** @param {string} src @param {string} label */
function player(src, label) {
  const item = document.createElement('audio');
  item.controls = true;
  item.preload = 'none';
  item.src = src;
  item.setAttribute('aria-label', label);
  return item;
}

/** @type {Person[]} */
let people = [];
/** @type {Sample[]} */
let samples = [];
let sourceGeneration = 0;
let personGeneration = 0;

async function refresh() {
  const data = await api('/api/samples');
  people = data.people;
  options(el('personSelect'), people, 'Choose a person');
  options(el('sourceSelect'), data.sources, 'Choose an imported recording');
  el('importButton').disabled = !data.installed;
  showStatus(
    data.installed ? 'Local media engine ready. No audio is uploaded to a cloud service.' : data.setup,
    !data.installed,
  );
  await loadPerson();
  await loadSource();
}

async function loadSource() {
  const generation = ++sourceGeneration;
  const key = el('sourceSelect').value;
  el('review').hidden = true;
  el('retry').hidden = true;
  el('importProgress').hidden = true;
  el('originalAudio').pause();
  el('dialogueAudio').pause();
  el('selectionAudio').pause();
  el('selectionAudio').ontimeupdate = null;
  el('selectionAudio').hidden = true;
  if (!key) {
    el('sourceStatus').textContent = 'Import a recording to review its speakers.';
    return;
  }
  for (;;) {
    /** @type {Source} */
    const source = await api(`/api/samples/sources/${key}`);
    if (generation !== sourceGeneration) return;
    el('sourceStatus').textContent = source.error || source.step;
    el('sourceStatus').classList.toggle('error', source.status === 'error');
    el('retry').hidden = source.status !== 'error';
    el('importProgress').hidden = source.status !== 'running';
    if (source.status === 'done') {
      el('review').hidden = false;
      el('originalAudio').src = `/api/samples/sources/${key}/audio/original`;
      el('dialogueAudio').src = `/api/samples/sources/${key}/audio/dialogue`;
      el('sourceStatus').textContent =
        `${source.segments.length} speaker turns. Source offset: ${source.start} seconds. ${source.separate ? 'Background separation applied.' : 'No background separation: both players contain the original window.'}`;
      el('turns').replaceChildren();
      if (!source.segments.length)
        el('turns').textContent = 'No speech turns detected. You can listen and select a range manually.';
      for (const turn of source.segments) {
        const item = button(
          `Speaker ${turn.speaker + 1}: ${turn.start.toFixed(1)} to ${turn.end.toFixed(1)} s${turn.overlap ? ' (overlap)' : ''}`,
          async () => {
            el('sampleStart').value = String(turn.start);
            el('sampleEnd').value = String(turn.end);
            el('sampleConsent').checked = false;
            el('sampleStart').focus();
          },
        );
        el('turns').append(item);
      }
      el('sampleStart').value = '0';
      el('sampleEnd').value = String(Math.min(5, source.duration));
      el('sampleConsent').checked = false;
      return;
    }
    if (source.status === 'error') return;
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }
}

function updateSelection() {
  const checked = new Set(
    Array.from(
      el('samples').querySelectorAll('input:checked'),
      (input) => /** @type {HTMLInputElement} */ (input).value,
    ),
  );
  const total = samples.filter((sample) => checked.has(sample.id)).reduce((sum, sample) => sum + sample.seconds, 0);
  el('selectionTotal').textContent = `${total.toFixed(2)} seconds selected. Choose 5 to 20 seconds total.`;
  el('buildVersion').disabled = !el('personSelect').value || total < 5 || total > 20;
  el('saveSample').disabled = !el('personSelect').value;
}

async function loadPerson() {
  const generation = ++personGeneration;
  const key = el('personSelect').value;
  samples = [];
  el('samples').replaceChildren();
  el('versions').replaceChildren();
  const who = people.find((person) => person.id === key);
  el('destination').textContent = who ? `Save to: ${who.name}` : 'Choose a person before saving.';
  el('collectionName').textContent = who ? `${who.name}: loading samples...` : 'Choose a person to see their samples.';
  el('sampleConsent').checked = false;
  updateSelection();
  if (!key) return;
  const data = await api(`/api/samples/people/${key}`);
  if (generation !== personGeneration) return;
  samples = data.samples;
  el('collectionName').textContent =
    `${data.name}: ${samples.length} approved samples. ${samples.length ? 'Check the samples for your next reference.' : 'Save a reviewed selection above to start.'}`;
  for (const sample of samples) {
    const li = document.createElement('li');
    const label = document.createElement('label');
    label.className = 'check';
    const check = document.createElement('input');
    check.type = 'checkbox';
    check.value = sample.id;
    check.addEventListener('change', updateSelection);
    label.append(
      check,
      `${sample.seconds.toFixed(2)} s from ${sample.source_name} (${sample.start.toFixed(2)} to ${sample.end.toFixed(2)} s)`,
    );
    const info = document.createElement('p');
    info.className = 'hint';
    info.textContent = `${sample.cleaned ? 'Dialogue' : 'Original'} audio. Level: ${sample.rms_db} dB RMS.${sample.clipped ? ' Possible clipping: consider another sample.' : ''}`;
    li.append(label, info, player(`/api/samples/audio/${sample.id}`, `Saved sample from ${sample.source_name}`));
    el('samples').append(li);
  }
  /** @type {Version[]} */
  const versions = data.versions;
  for (const version of versions) {
    const li = document.createElement('li');
    const title = document.createElement('strong');
    title.textContent = `${version.name}${data.active === version.id ? ' (preferred)' : ''}`;
    const actions = document.createElement('div');
    actions.className = 'row';
    const audio = player('', `Comparison for ${version.name}`);
    audio.removeAttribute('src');
    audio.hidden = true;
    actions.append(
      button('Preview comparison', async () => {
        const form = new FormData();
        form.set('voice', version.id);
        form.set('text', el('previewText').value);
        const job = await api('/api/clone/preview', { method: 'POST', body: form });
        showStatus(`Rendering ${version.name}. Local CPU rendering can take several minutes.`);
        for (let attempt = 0; attempt < 600; attempt++) {
          await new Promise((resolve) => setTimeout(resolve, 2000));
          const result = await api(`/api/clone/preview/${job.job}`);
          if (result.status === 'error') throw new Error(result.error);
          if (result.status === 'done') {
            audio.src = `/api/clone/preview/${job.job}/audio`;
            audio.hidden = false;
            showStatus(`Comparison ready: ${version.name}. Press play to listen.`);
            return;
          }
        }
        throw new Error('Preview is taking longer than expected. Check the local server before retrying.');
      }),
    );
    if (data.active !== version.id)
      actions.append(
        button('Mark preferred', async () => {
          await post(`/api/samples/people/${key}/active`, { voice: version.id });
          await loadPerson();
          showStatus(`${version.name} is preferred. Existing Studio scripts are unchanged.`);
        }),
      );
    li.append(title, actions, audio);
    el('versions').append(li);
  }
  if (!versions.length) el('versions').textContent = 'No reference versions yet.';
  updateSelection();
}

el('refresh').addEventListener('click', () => void run(el('refresh'), refresh));
el('sourceSelect').addEventListener('change', () => void run(null, loadSource));
el('personSelect').addEventListener('change', () => void run(null, loadPerson));
el('importForm').addEventListener('submit', (event) => {
  event.preventDefault();
  void run(el('importButton'), async () => {
    const form = new FormData(el('importForm'));
    if (!el('mediaFile').files.length) form.delete('file');
    showStatus('Uploading to the local app. Keep this page open until the upload finishes.');
    const result = await api('/api/samples/sources', { method: 'POST', body: form });
    const data = await api('/api/samples');
    options(el('sourceSelect'), data.sources, 'Choose an imported recording');
    el('sourceSelect').value = result.id;
    showStatus('Import accepted. Analyzing locally; you can revisit the saved source after a refresh.');
    await loadSource();
  });
});
el('personForm').addEventListener('submit', (event) => {
  event.preventDefault();
  void run(/** @type {HTMLButtonElement} */ (event.submitter), async () => {
    const data = new FormData(el('personForm'));
    const person = await post('/api/samples/people', { name: data.get('name'), consent: data.has('consent') });
    people.unshift(person);
    options(el('personSelect'), people, 'Choose a person');
    el('personSelect').value = person.id;
    el('personForm').reset();
    await loadPerson();
    showStatus(`Created collection: ${person.name}.`);
  });
});
el('retry').addEventListener(
  'click',
  () =>
    void run(el('retry'), async () => {
      await post(`/api/samples/sources/${el('sourceSelect').value}/retry`, {});
      await loadSource();
    }),
);
el('listen').addEventListener(
  'click',
  () =>
    void run(el('listen'), async () => {
      const audio = el('selectionAudio');
      audio.pause();
      audio.ontimeupdate = null;
      el('originalAudio').pause();
      el('dialogueAudio').pause();
      audio.src = el('useCleaned').checked ? el('dialogueAudio').src : el('originalAudio').src;
      audio.hidden = false;
      const start = Number(el('sampleStart').value);
      const end = Number(el('sampleEnd').value);
      if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end <= start)
        throw new Error('Choose a valid selection start and end.');
      audio.currentTime = start;
      await audio.play();
      audio.onpause = () => {
        audio.ontimeupdate = null;
      };
      audio.ontimeupdate = () => {
        if (audio.currentTime >= end) {
          audio.ontimeupdate = null;
          audio.pause();
        }
      };
    }),
);
el('sampleForm').addEventListener('submit', (event) => {
  event.preventDefault();
  void run(el('saveSample'), async () => {
    await post(`/api/samples/people/${el('personSelect').value}/samples`, {
      source: el('sourceSelect').value,
      start: Number(el('sampleStart').value),
      end: Number(el('sampleEnd').value),
      cleaned: el('useCleaned').checked,
      consent: el('sampleConsent').checked,
    });
    await loadPerson();
    showStatus('Approved sample saved. The original recording and previous reference versions are unchanged.');
  });
});
el('buildVersion').addEventListener(
  'click',
  () =>
    void run(el('buildVersion'), async () => {
      const selected = Array.from(
        el('samples').querySelectorAll('input:checked'),
        (input) => /** @type {HTMLInputElement} */ (input).value,
      );
      const version = await post(`/api/samples/people/${el('personSelect').value}/versions`, { samples: selected });
      await loadPerson();
      showStatus(
        `Created ${version.name}. Compare it before marking it preferred. This is a new reference, not model training.`,
      );
    }),
);
for (const id of /** @type {const} */ (['sampleStart', 'sampleEnd', 'useCleaned'])) {
  el(id).addEventListener('change', () => {
    el('sampleConsent').checked = false;
  });
}
void run(null, refresh);
