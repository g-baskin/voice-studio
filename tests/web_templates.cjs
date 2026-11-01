// Exercise the Clean page's TypeScript logic directly (Node type stripping); no browser install needed.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const lib = path.join(__dirname, '../frontend/src/lib/clean');
const page = fs.readFileSync(path.join(__dirname, '../frontend/src/routes/+page.svelte'), 'utf8');
const presets = JSON.parse(process.argv[2]);
const keys = ['ai_clean', 'dereverb', 'demetal', 'deharsh', 'warmth', 'denoise', 'room_tone'];
const load = (name) => import(pathToFileURL(path.join(lib, name)).href);

function file(name, size = 100) {
  return new File([new Uint8Array(size)], name);
}

(async () => {
  const t = await load('templates.ts');
  const q = await load('queue.ts');
  const v = await load('voices.ts');
  assert.deepEqual(
    t.SLIDERS.map(([k]) => k),
    keys,
  );
  for (const [k] of t.SLIDERS) assert.ok(page.includes('id="s-{key}"') && page.includes('id="v-{key}"'), k);
  const ready = t.validatePresets(presets);
  const expected = {
    clean: [0, 0, 0.25, 0.2, 0.25, 0, 0],
    ad: [1, 0.3, 0.7, 0.6, 0.5, 0, 0],
    metallic: [0, 0, 0.85, 0.4, 0.35, 0, 0],
    echo: [1, 0.6, 0.4, 0.3, 0.25, 0, 0],
    noise: [1, 0, 0.25, 0.2, 0.25, 0.2, 0],
    strong: [1, 0.6, 1, 0.9, 0.7, 0, 0],
  };
  assert.deepEqual(
    t.TEMPLATES.map((x) => x.key),
    Object.keys(expected),
  );
  assert.equal(t.DEFAULT_TEMPLATE, 'ad');
  for (const [name, values] of Object.entries(expected)) {
    const template = t.templateFor(name, {});
    const settings = t.settingsFor(template, ready);
    keys.forEach((k, i) => {
      assert.equal(settings[k], values[i], `${name}: ${k}`);
      assert.equal(t.percent(settings[k]), `${Math.round(values[i] * 100)}%`);
    });
    assert.ok(template.description.length > 10);
    // Every control resets, including a room-tone override from a previous run.
    const edited = { ...settings };
    keys.forEach((k) => (edited[k] = 0.95));
    assert.deepEqual(t.settingsFor(template, ready), settings);
    // The upload uses what is displayed, not hidden preset defaults.
    const sent = q.cleanForm(
      file('voice.wav'),
      'clean',
      { preset: template.preset, controls: settings, label: name },
      {
        start: 0,
        seconds: 15,
      },
    );
    keys.forEach((k, i) => assert.equal(Number(sent.get(k)), values[i]));
    assert.equal(sent.get('preset'), template.preset);
    assert.equal(sent.get('mode'), 'clean');
  }
  const custom = { ...t.settingsFor(t.templateFor('ad', {}), ready), warmth: 0.15 };
  const form = q.cleanForm(
    file('voice.wav'),
    'clean',
    { preset: 'standard', controls: custom, label: 'x' },
    {
      start: 0,
      seconds: 15,
    },
  );
  assert.equal(Number(form.get('warmth')), 0.15);

  // Saved templates: same storage key and shape; invalid entries are dropped, room tone is kept.
  assert.equal(t.SAVED_KEY, 'naturalvoice.templates.v1');
  const good = {
    name: '<b>Mine</b>',
    preset: 'light',
    settings: { ...expected.clean.reduce((o, x, i) => ({ ...o, [keys[i]]: x }), {}), room_tone: 0.05 },
  };
  const saved = t.parseSaved(
    JSON.stringify({
      'saved-abc': good,
      bad: good,
      'saved-x': { ...good, preset: 'loud' },
      'saved-y': { ...good, settings: { ...good.settings, warmth: 2 } },
    }),
  );
  assert.deepEqual(Object.keys(saved), ['saved-abc']);
  assert.equal(t.settingsFor(t.templateFor('saved-abc', saved), ready).room_tone, 0.05);
  assert.equal(t.templateLabel('saved-abc', saved), 'Saved: <b>Mine</b>');
  assert.deepEqual(t.parseSaved('{oops'), {});
  assert.deepEqual(t.parseSaved('[1]'), {});
  assert.equal(t.templateFor('constructor', {}), undefined);

  // Loading failure: incomplete settings throw, and nothing can run before settings load.
  assert.throws(() => t.validatePresets({ light: {} }), /Incomplete/);
  const base = {
    templatesReady: false,
    hasFile: true,
    busy: false,
    queue: [],
    savedSelected: false,
    downloading: false,
  };
  assert.equal(q.actions(base).run, true, 'Do not upload before settings load');
  assert.equal(q.actions(base).settings, true);
  assert.equal(q.actions({ ...base, templatesReady: true }).run, false);
  assert.equal(q.actions({ ...base, templatesReady: true, busy: true }).run, true);
  assert.equal(q.actions({ ...base, templatesReady: true, hasFile: false }).run, true);

  // File handling: supported types, size limits and the 20-file queue cap.
  const picked = q.acceptFiles(0, [file('ad.mp4'), file('notes.txt'), file('empty.wav', 0)]);
  assert.deepEqual(
    picked.accepted.map((x) => x.file.name),
    ['ad.mp4'],
  );
  assert.deepEqual(picked.rejected, ['notes.txt: unsupported type.', 'empty.wav: empty or larger than 500 MB.']);
  assert.deepEqual(q.acceptFiles(20, [file('a.wav')]).rejected, ['Queue limit: 20 files.']);
  assert.throws(() => q.section(0, 25), /length from 10 to 20/);
  assert.deepEqual(q.section(1, 15), { start: 1, seconds: 15 });

  // Job polling reports progress and surfaces server errors.
  const replies = [
    { job: 'j1' },
    { status: 'running', progress: 0.5, step: 'Cleaning' },
    { status: 'done', progress: 1, result: { mode: 'clean' } },
  ];
  const seen = [];
  const done = await q.runJob(
    { file: file('voice.wav') },
    'clean',
    { preset: 'standard', controls: custom, label: 'x' },
    { start: 0, seconds: 15 },
    {
      fetch: async (url) => {
        seen.push(url);
        return new Response(JSON.stringify(replies.shift()));
      },
      status() {},
      progress() {},
      wait: async () => {},
    },
  );
  assert.deepEqual(seen, ['/api/clean', '/api/jobs/j1', '/api/jobs/j1']);
  assert.equal(done.job, 'j1');
  await assert.rejects(
    q.responseJSON(new Response('{"detail":"Intercepted test upload"}', { status: 400 })),
    /Intercepted test upload/,
  );
  await assert.rejects(q.responseJSON(new Response('nope', { status: 500 })), /unreadable/);

  // Results table and voice grouping.
  const rows = q.metricRows({ listener: 3, metallic: 5, echo_db: null }, { listener: 3.5, metallic: 6, echo_db: -40 });
  assert.equal(rows[0].tone, 'good');
  assert.equal(rows[3].tone, 'worse');
  assert.equal(rows[2].before, 'Unavailable');
  assert.equal(q.batchSummary(2, 1, true).startsWith('2 completed, 1 failed. Stopped'), true);
  const catalog = [
    { id: 'af_heart', name: 'Heart', kind: 'stock', language: 'en', gender: 'f' },
    { id: 'c1', name: '<i>Me</i>', kind: 'clone' },
  ];
  assert.deepEqual(
    v.voiceGroups(catalog).map((g) => g.label),
    ['Stock voices', 'Cloned voices'],
  );
  assert.equal(v.voiceGroups(catalog)[1].voices[0].text, '<i>Me</i>');
  assert.equal(v.defaultVoice(catalog), 'af_heart');
  assert.equal(v.voiceGroups([{ ...catalog[1], starred: true }])[0].label, '\u2605 Starred');
  console.log(
    'Six templates: controls, percentages, reset, manual overrides, upload payloads, loading failure, saved templates, queue limits, job polling and voices passed.',
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
