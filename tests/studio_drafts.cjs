// Studio drafts can come from a restored backup: damaged ones must load as safe defaults, not break the page.
const assert = require('node:assert/strict');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

(async () => {
  const { toEditor, normalLine, MAX_LINES } = await import(
    pathToFileURL(path.join(__dirname, '../frontend/src/lib/studio/logic.ts')).href
  );

  // An older draft keeps its values, and missing fields get the usual defaults.
  const kept = toEditor({ title: 'Mine', lines: [{ id: 'abc', text: 'Hi', voice: 'bf_emma', speed: 1.2 }] });
  assert.equal(kept.title, 'Mine');
  assert.equal(kept.lines[0].id, 'abc');
  assert.equal(kept.lines[0].text, 'Hi');
  assert.equal(kept.lines[0].voice, 'bf_emma');
  assert.equal(kept.lines[0].speed, 1.2);
  assert.equal(kept.lines[0].pause, 0.4);
  assert.deepEqual(kept.lines[0].takes, [0]);

  // Wrong types and junk entries become defaults instead of reaching the editor.
  const damaged = toEditor({
    title: 42,
    lines: [null, 'text', { text: 7, voice: [], speed: 'fast', takes: ['x', 2], take: 9, start: 'soon' }],
    dictionary: { ok: 'fine', bad: 3 },
    cast: ['not', 'a', 'map'],
    mode: 'weird',
  });
  assert.equal(damaged.title, 'Untitled project');
  assert.equal(damaged.lines.length, 3);
  for (const line of damaged.lines) {
    assert.equal(typeof line.text, 'string');
    assert.equal(typeof line.voice, 'string');
    assert.ok(line.voice.length > 0);
    assert.ok(Number.isFinite(line.speed));
    assert.ok(line.takes.includes(line.take));
  }
  assert.deepEqual(damaged.lines[2].takes, [2]);
  assert.equal(damaged.lines[2].take, 2);
  assert.equal(damaged.lines[2].start, null);
  assert.deepEqual(damaged.dictionary, [['ok', 'fine']]);
  assert.deepEqual(damaged.cast, {});
  assert.equal(damaged.mode, 'sequential');

  // A non-array lines value and oversized drafts are bounded.
  assert.deepEqual(toEditor({ lines: { 0: 'x' } }).lines, []);
  assert.equal(toEditor({ lines: Array.from({ length: MAX_LINES + 5 }, () => ({})) }).lines.length, MAX_LINES);
  assert.equal(normalLine(undefined).text, '');
  console.log('Studio draft checks passed: older drafts kept, damaged drafts made safe, size bounded.');
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
