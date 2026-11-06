// Run only against a server with disposable NATURALVOICE_DATA. Writes synthetic media and sequences.
const chromium = require('./browser_support.cjs');
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const BASE = process.env.NV_URL || 'http://127.0.0.1:8776';
const OUT = process.env.NV_SCREENSHOTS || '/tmp/editor-browser';

function fixture(dir) {
  const file = path.join(dir, 'Interview take 1.mp4');
  execFileSync('ffmpeg', [
    '-y',
    '-v',
    'error',
    '-f',
    'lavfi',
    '-i',
    'testsrc2=s=640x360:r=30:d=6',
    '-f',
    'lavfi',
    '-i',
    'sine=f=330:d=6',
    '-c:v',
    'libx264',
    '-pix_fmt',
    'yuv420p',
    '-c:a',
    'aac',
    '-shortest',
    file,
  ]);
  return file;
}

// Bars then a test pattern (a scene change at 6 s), with a tone that is silent from 4 to 5.5 s.
function talkFixture(dir) {
  const file = path.join(dir, 'Talk.mp4');
  execFileSync('ffmpeg', [
    '-y',
    '-v',
    'error',
    '-f',
    'lavfi',
    '-i',
    'smptebars=s=640x360:r=30:d=6',
    '-f',
    'lavfi',
    '-i',
    'testsrc2=s=640x360:r=30:d=6',
    '-f',
    'lavfi',
    '-i',
    'sine=f=330:d=12',
    '-filter_complex',
    "[0:v][1:v]concat=n=2:v=1:a=0,format=yuv420p[v];[2:a]volume=0:enable='between(t,4,5.5)'[a]",
    '-map',
    '[v]',
    '-map',
    '[a]',
    '-c:v',
    'libx264',
    '-c:a',
    'aac',
    file,
  ]);
  return file;
}

const FPS = 30;
const secs = (tc) => {
  const [h, m, s, f] = tc.trim().split(':').map(Number);
  return h * 3600 + m * 60 + s + f / FPS;
};
const clips = (page) => page.locator('[data-clip]');
const height = (loc) => loc.evaluate((el) => el.getBoundingClientRect().height);

async function drag(page, loc, dx, dy) {
  const box = await loc.boundingBox();
  const x = box.x + box.width / 2;
  const y = box.y + box.height / 2;
  await page.mouse.move(x, y);
  await page.mouse.down();
  for (let i = 1; i <= 8; i++) await page.mouse.move(x + (dx * i) / 8, y + (dy * i) / 8);
  await page.mouse.up();
}

// Scrolling, zooming, resizing and slipping a clip back to its first frame.
async function timelineGestures(page) {
  const scroller = page.locator('.timeline .scroll');
  const zoom = page.getByLabel('Timeline zoom');
  await page.locator('body').click({ position: { x: 5, y: 890 } });
  await page.keyboard.press('Escape');
  for (let i = 0; i < 4; i++) await page.keyboard.press('=');
  const lane = page.locator('[data-lane="v1"]');
  const laneBox = await lane.boundingBox();
  await page.mouse.move(laneBox.x + 400, laneBox.y + laneBox.height / 2);
  const left0 = await scroller.evaluate((el) => el.scrollLeft);
  await page.mouse.wheel(0, 300);
  await page.waitForFunction((l) => document.querySelector('.timeline .scroll').scrollLeft > l, left0);
  const zoom0 = Number(await zoom.inputValue());
  await page.keyboard.down('Control');
  await page.mouse.wheel(0, -200);
  await page.keyboard.up('Control');
  assert.ok(Number(await zoom.inputValue()) > zoom0, 'Ctrl+wheel zooms in');
  assert.equal(await page.evaluate(() => window.scrollY), 0);
  await page.keyboard.press('\\');
  await page.waitForFunction(() => document.querySelector('.timeline .scroll').scrollLeft === 0);
  assert.equal(await scroller.evaluate((el) => el.scrollLeft), 0, 'fit shows the very beginning');

  // A track's bottom edge makes it taller; double-click puts it back.
  const h0 = await height(lane);
  const handle = page.getByRole('slider', { name: 'Height of V1' });
  await drag(page, handle, 0, 40);
  assert.ok(Math.abs((await height(lane)) - (h0 + 40)) <= 2, 'track grows with the drag');
  await handle.dblclick();
  assert.equal(await height(lane), h0);

  // Slip slides the content under a clip without moving it, and stops at the source's first frame.
  const piece = clips(page).filter({ hasText: 'Interview' }).nth(1);
  await piece.click();
  const sourceIn = page.getByLabel('Source in (s)');
  assert.equal(await sourceIn.inputValue(), '2.000');
  const label = await piece.getAttribute('aria-label');
  await page.keyboard.press('y');
  await drag(page, piece, 120, 0);
  const slipped = Number(await sourceIn.inputValue());
  assert.ok(slipped > 0 && slipped < 2, `slipped part way to ${slipped}`);
  await drag(page, piece, 400, 0);
  assert.equal(await sourceIn.inputValue(), '0.000');
  assert.equal(await piece.getAttribute('aria-label'), label);
  await page.keyboard.press(process.platform === 'darwin' ? 'Meta+z' : 'Control+z');
  assert.equal(await sourceIn.inputValue(), slipped.toFixed(3));
  await page.getByRole('menuitem', { name: 'Clip' }).click();
  await page.getByRole('menuitem', { name: 'Slip to first frame' }).click();
  assert.equal(await sourceIn.inputValue(), '0.000');
  await page.keyboard.press('v');

  // The bar above the timeline trades room between the preview and the timeline, and is remembered.
  const timeline = page.locator('.editor > .timeline');
  const t0 = await height(timeline);
  const split = page.getByRole('slider', { name: 'Timeline height' });
  await drag(page, split, 0, -120);
  assert.ok(Math.abs((await height(timeline)) - (t0 + 120)) <= 2, 'timeline grows with the drag');
  assert.ok(Number(await page.evaluate(() => localStorage.getItem('sharkaudio.editor.timelineHeight'))) > t0);
  await split.dblclick();
  assert.equal(await height(timeline), t0);
  await page.waitForFunction(() => document.querySelector('.save')?.textContent === 'All changes saved');
}

// V1 clips as [start, seconds], in timeline order.
async function v1(page) {
  const labels = await clips(page).evaluateAll((els) =>
    els.map((e) => e.getAttribute('aria-label') ?? '').filter((l) => l.includes(' on V1,')),
  );
  return labels
    .map((l) => {
      const m = l.match(/starts (\S+), ([\d.]+) seconds/);
      return [+secs(m[1]).toFixed(2), +m[2]];
    })
    .sort((a, b) => a[0] - b[0]);
}

async function newSequence(page) {
  await page.getByRole('menuitem', { name: 'File', exact: true }).click();
  await page.getByRole('menuitem', { name: /New sequence/ }).click();
  await page.waitForFunction(() => document.querySelector('.save')?.textContent === 'All changes saved');
}

async function loadSource(page) {
  const item = page.getByRole('button', { name: /^Talk\.mp4: press Enter/ }).first();
  await item.focus();
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => {
    const video = document.querySelector('.monitor video');
    return video instanceof HTMLVideoElement && video.readyState >= 2;
  });
}

// Analysis shares the processing slot with uploads, so a busy slot shows an alert and the button is retried.
async function analyse(panel, name, ready) {
  for (let i = 0; i < 20; i++) {
    await panel.getByRole('button', { name }).click();
    try {
      await ready.waitFor({ timeout: 3000 });
      return;
    } catch {
      if (!(await panel.getByRole('alert').count())) {
        await ready.waitFor({ timeout: 60000 });
        return;
      }
    }
  }
  throw new Error(`${name} never ran`);
}

// Drags from the middle of a locator, calling during() before the button is released.
async function dragX(page, loc, dx, during) {
  const b = await loc.boundingBox();
  const x = b.x + b.width / 2;
  const y = b.y + b.height / 2;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x + dx / 2, y, { steps: 4 });
  await page.mouse.move(x + dx, y, { steps: 4 });
  if (during) await during();
  await page.mouse.up();
}

// Clip mode: source viewer, three-point edits, trims, shuttle, subclips, analysis, reframing and batch export.
async function clipMode(page, scheme, talk, dir) {
  await page.goto(BASE + '/editor?mode=edit');
  await page.waitForFunction(() => document.querySelector('.save')?.textContent === 'All changes saved');
  const modes = page.getByRole('group', { name: 'Editor mode' });
  const mon = page.getByRole('region', { name: 'Source monitor' });
  const prog = page.getByRole('region', { name: 'Program monitor' });
  const panel = page.getByRole('complementary', { name: 'Clip tools' });
  const tl = page.getByRole('region', { name: 'Timeline' });
  const length = async () => secs(await page.getByLabel('Sequence length').textContent());
  const undo = () => page.keyboard.press('ControlOrMeta+z');
  const focusSource = () => mon.getByText('Source', { exact: true }).click();
  const focusProgram = () => prog.getByText('Program', { exact: true }).click();
  const frames = async (n) => {
    for (let i = 0; i < n; i++) await page.keyboard.press('Shift+ArrowRight');
  };

  // The mode is a switch in the header, kept in the URL and remembered across visits.
  assert.equal(await modes.getByRole('button', { name: 'Edit' }).getAttribute('aria-pressed'), 'true');
  assert.equal(await mon.count(), 0);
  await modes.getByRole('button', { name: 'Clip' }).click();
  assert.match(page.url(), /mode=clip/);
  await page.goto(BASE + '/editor');
  await page.waitForFunction(() => document.querySelector('.save')?.textContent === 'All changes saved');
  assert.equal(await modes.getByRole('button', { name: 'Clip' }).getAttribute('aria-pressed'), 'true');
  await mon.waitFor();

  if (scheme === 'light') {
    await page.locator('.bin input[type=file]').setInputFiles(talk);
    await page.waitForFunction(
      () =>
        [...document.querySelectorAll('.bin .item')].some(
          (e) => e.textContent.includes('Talk.mp4') && e.textContent.includes('640×360'),
        ),
      null,
      { timeout: 60000 },
    );
  }
  await newSequence(page);
  await loadSource(page);

  // Source In 0, Out 2 s: overwrite, append, then insert at the start ripples the rest along.
  await focusSource();
  await page.keyboard.press('Home');
  await page.keyboard.press('i');
  await frames(6);
  await page.keyboard.press('o');
  await page.keyboard.press('.');
  await page.keyboard.press('Shift+.');
  assert.equal(await length(), 4);
  await focusProgram();
  await page.keyboard.press('Home');
  await focusSource();
  await page.keyboard.press(',');
  assert.equal(await length(), 6);
  assert.deepEqual(await v1(page), [
    [0, 2],
    [2, 2],
    [4, 2],
  ]);
  // Overwrite at the start replaces without lengthening; undo puts the original back.
  await focusProgram();
  await page.keyboard.press('Home');
  await focusSource();
  await page.keyboard.press('.');
  assert.equal(await length(), 6);
  assert.equal((await v1(page)).length, 3);
  await undo();
  // Cmd/Ctrl+U saves the source marks as a subclip.
  await page.keyboard.press('ControlOrMeta+u');
  await panel.getByRole('tab', { name: 'Subclips' }).click();
  assert.equal(await panel.getByRole('list', { name: 'Subclips' }).getByRole('listitem').count(), 1);

  // Sequence In 0, Out 1 s: extract closes the gap, lift leaves it.
  await focusProgram();
  await page.keyboard.press('Home');
  await page.keyboard.press('i');
  await frames(3);
  await page.keyboard.press('o');
  await page.keyboard.press("'");
  assert.equal(await length(), 5);
  await undo();
  assert.equal(await length(), 6);
  await page.keyboard.press(';');
  assert.equal(await length(), 6);
  assert.deepEqual((await v1(page))[0], [1, 1]);
  await undo();
  // Reverse three-point: only a source In, so the clip is back-timed into the 1 s sequence span.
  await focusSource();
  await page.keyboard.press('Alt+x');
  await page.keyboard.press('Home');
  await frames(9);
  await page.keyboard.press('i');
  await page.keyboard.press('.');
  assert.equal(await length(), 6);
  assert.deepEqual((await v1(page)).slice(0, 2), [
    [0, 1],
    [1, 1],
  ]);
  await undo();
  assert.deepEqual(await v1(page), [
    [0, 2],
    [2, 2],
    [4, 2],
  ]);

  // W ripple-trims the next edit back to the playhead; Alt+W trims and leaves a gap.
  await focusProgram();
  await page.keyboard.press('Alt+x');
  await page.keyboard.press('Home');
  await frames(3);
  await page.keyboard.press('w');
  assert.equal(await length(), 5);
  await undo();
  await page.keyboard.press('Alt+w');
  assert.equal(await length(), 6);
  await undo();
  assert.equal(await length(), 6);

  // Tool keys.
  for (const [key, name] of [
    ['b', 'Ripple'],
    ['n', 'Roll'],
    ['u', 'Slide'],
    ['v', 'Select'],
  ]) {
    await page.keyboard.press(key);
    assert.equal(await tl.getByRole('button', { name, exact: true }).getAttribute('aria-pressed'), 'true', name);
  }

  // J/K/L shuttle: L twice is 2×, J turns round, K stops.
  const rate = prog.getByLabel('Shuttle speed');
  await page.keyboard.press('Home');
  await page.keyboard.press('l');
  await page.keyboard.press('l');
  await rate.filter({ hasText: '▶ 2×' }).waitFor({ timeout: 2000 });
  // Reverse from the end, so playback has room before it reaches the start.
  await page.keyboard.press('k');
  await page.keyboard.press('End');
  await page.keyboard.press('j');
  await page.keyboard.press('j');
  await rate.filter({ hasText: '◀ 2×' }).waitFor({ timeout: 2000 });
  await page.keyboard.press('k');
  await rate.waitFor({ state: 'detached' });
  await page.keyboard.press('Home');

  // Roll keeps the length and shows outgoing | incoming frames; ripple moves later clips; slide keeps its own length.
  const snap = tl.getByRole('button', { name: 'Snap' });
  if ((await snap.getAttribute('aria-pressed')) === 'true') await snap.click();
  const ids = await clips(page).evaluateAll((els) =>
    els
      .filter((e) => (e.getAttribute('aria-label') ?? '').includes(' on V1,'))
      .sort((a, b) => a.offsetLeft - b.offsetLeft)
      .map((e) => e.dataset.clip),
  );
  const pxPerSec = (await page.locator(`[data-clip="${ids[0]}"]`).boundingBox()).width / 2;
  const firstEnd = page.locator(`[data-clip="${ids[0]}"] .edge.end`);
  await tl.getByRole('button', { name: 'Roll', exact: true }).click();
  await dragX(page, firstEnd, pxPerSec / 2, async () => {
    await page.locator('.trim-labels').waitFor();
    assert.match(await page.locator('.trim-labels').textContent(), /Outgoing.*Incoming/s);
    await page.screenshot({ path: path.join(OUT, `clip-trim-${scheme}.png`) });
  });
  assert.equal(await page.locator('.trim-labels').count(), 0);
  assert.deepEqual(await v1(page), [
    [0, 2.5],
    [2.5, 1.5],
    [4, 2],
  ]);
  await tl.getByRole('button', { name: 'Ripple', exact: true }).click();
  await dragX(page, firstEnd, -pxPerSec / 2);
  assert.deepEqual(await v1(page), [
    [0, 2],
    [2, 1.5],
    [3.5, 2],
  ]);
  await tl.getByRole('button', { name: 'Slide', exact: true }).click();
  await dragX(page, page.locator(`[data-clip="${ids[1]}"]`), pxPerSec / 2);
  assert.deepEqual(await v1(page), [
    [0, 2.5],
    [2.5, 1.5],
    [4, 1.5],
  ]);
  await tl.getByRole('button', { name: 'Select', exact: true }).click();
  await page.locator('body').click({ position: { x: 5, y: 890 } });
  for (let i = 0; i < 3; i++) await undo();
  assert.deepEqual(await v1(page), [
    [0, 2],
    [2, 2],
    [4, 2],
  ]);

  // A fresh sequence holding the whole file for analysis.
  await newSequence(page);
  await loadSource(page);
  await mon.getByRole('button', { name: 'Append' }).click();
  assert.equal(await length(), 12);

  // The file's last 6 s (no silence) also on V2 at the start, so V2 plays other moments of it under V1's pause.
  await tl.getByRole('button', { name: 'Target V2 for source picture' }).click();
  await focusSource();
  await page.keyboard.press('Alt+x');
  await page.keyboard.press('Home');
  await frames(18);
  await page.keyboard.press('i');
  await focusProgram();
  await page.keyboard.press('Home');
  await focusSource();
  await page.keyboard.press('.');
  await tl.getByRole('button', { name: 'Target V1 for source picture' }).click();
  await page.locator('body').click({ position: { x: 5, y: 890 } });
  await page.keyboard.press('Escape');
  const onV2 = () =>
    clips(page).evaluateAll((els) =>
      els.map((e) => e.getAttribute('aria-label') ?? '').filter((l) => l.includes(' on V2,')),
    );
  assert.equal((await onV2()).length, 1);

  // Remove silences: the 1.5 s gap less padding comes out of V1 only, as one undo step.
  await panel.getByRole('tab', { name: 'Silences' }).click();
  await panel.getByLabel('File').selectOption({ label: 'Talk.mp4' });
  const boxes = panel.getByRole('list', { name: 'Silences to remove' }).getByRole('checkbox');
  await analyse(panel, 'Find silences', boxes.first());
  assert.equal(await boxes.count(), 1);
  await panel.getByRole('button', { name: /^Remove 1 silence/ }).click();
  const cut = 12 - (await length());
  assert.ok(cut > 1.0 && cut < 1.5, `silence removed ${cut}`);
  assert.equal((await v1(page)).length, 2);
  const v2 = await onV2();
  assert.ok(v2.length === 1 && /6\.00 seconds/.test(v2[0]), `V2 is not silent there and stays whole: ${v2}`);
  await undo();
  await undo();
  assert.equal(await length(), 12);
  assert.equal((await onV2()).length, 0);

  // Scenes: the cut at 6 s, kept as markers.
  await panel.getByRole('tab', { name: 'Scenes' }).click();
  const chips = panel.getByRole('list', { name: 'Scene changes' }).getByRole('button');
  await analyse(panel, 'Find scene changes', chips.first());
  const scenes = (await chips.allTextContents()).map(secs);
  assert.ok(
    scenes.some((t) => Math.abs(t - 6) < 0.1),
    `scenes ${scenes}`,
  );
  await panel.getByRole('button', { name: 'Add as markers' }).click();

  // Moments are ranked, labelled as a heuristic, and open in the source viewer.
  await panel.getByRole('tab', { name: 'Moments' }).click();
  await panel.getByText(/ranked by energy and pace/).waitFor();
  await panel.getByLabel('Shortest (s)').fill('2');
  await panel.getByLabel('Longest (s)').fill('4');
  await panel.getByLabel('How many').fill('3');
  const moments = panel.getByRole('list', { name: 'Moments' }).getByRole('listitem');
  await analyse(panel, 'Find moments', moments.first());
  const found = await moments.count();
  assert.ok(found >= 1 && found <= 3, `moments ${found}`);
  await moments.first().getByRole('button', { name: 'Open in source' }).click();
  assert.match(await mon.locator('.tc.muted').textContent(), /In–Out/);
  await page.screenshot({ path: path.join(OUT, `clip-${scheme}.png`) });

  // 9:16 makes the canvas vertical, and dragging the reframe box moves the picture.
  await prog.getByRole('button', { name: '9:16' }).click();
  const [w, h] = await prog.locator('canvas').evaluate((c) => [c.width, c.height]);
  assert.ok(h > w, `vertical canvas ${w}x${h}`);
  await prog.getByRole('button', { name: 'Go to start' }).click();
  await prog.getByRole('button', { name: 'Reframe', exact: true }).click();
  const frame = prog.getByRole('button', { name: /^Reframe Talk\.mp4/ });
  await frame.waitFor();
  await dragX(page, frame, (await frame.boundingBox()).width * 0.25);
  assert.match(await frame.textContent(), /x 0\.25/);
  await undo();
  assert.match(await frame.textContent(), /x 0\.00/);
  await page.screenshot({ path: path.join(OUT, `clip-vertical-${scheme}.png`) });
  await prog.getByRole('button', { name: 'Reframe', exact: true }).click();
  await prog.getByRole('button', { name: '16:9' }).click();

  if (scheme === 'light') {
    // Batch export: markers at 0 s and the 6 s scene cut give two files, the second 6 s long.
    await focusProgram();
    await page.keyboard.press('Home');
    await page.keyboard.press('m');
    await page.waitForFunction(() => document.querySelector('.save')?.textContent === 'All changes saved');
    await page.getByRole('button', { name: 'Export', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: 'Export' });
    await dialog.getByLabel('Quality').selectOption('draft');
    await dialog.getByRole('radio', { name: /Each marker to the next.*\(2\)/ }).check();
    await dialog.getByRole('button', { name: 'Export 2 files' }).click();
    await dialog.getByText(/All 2 files exported/).waitFor({ timeout: 120000 });
    const links = dialog.getByRole('list', { name: 'Exported files' }).getByRole('link');
    assert.equal(await links.count(), 2);
    const download = await Promise.all([page.waitForEvent('download'), links.nth(1).click()]).then(([d]) => d);
    const second = path.join(dir, 'second.mp4');
    await download.saveAs(second);
    const seconds = Number(
      execFileSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', second], {
        encoding: 'utf8',
      }),
    );
    assert.ok(Math.abs(seconds - 6) < 0.2, `second file ${seconds}`);
    await dialog.getByRole('button', { name: 'Close' }).click();
  }
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
}

// A seeded transcript for Talk.mp4: the shared caption fixture's words, then a filler and two more sentences.
const CAPTION_CASE = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures', 'caption_pages.json'), 'utf8'))
  .cases[0];
const TALK_WORDS = [
  ...CAPTION_CASE.words,
  [6.0, 6.3, 'um'],
  [6.3, 6.6, 'You'],
  [6.6, 6.9, 'can'],
  [6.9, 7.2, 'cut'],
  [7.2, 7.5, '3'],
  [7.5, 7.9, 'words.'],
  [9.0, 9.4, 'But'],
  [9.4, 9.8, 'this'],
  [9.8, 10.4, 'works.'],
];

// One output frame as raw RGB, scaled down so frames are cheap to compare.
const frameAt = (file, t) =>
  execFileSync(
    'ffmpeg',
    ['-v', 'error', '-ss', String(t), '-i', file, '-frames:v', '1', '-s', '320x180'].concat([
      '-f',
      'rawvideo',
      '-pix_fmt',
      'rgb24',
      '-',
    ]),
  );
const changed = (a, b) => {
  let n = 0;
  for (let i = 0; i < a.length; i++) if (Math.abs(a[i] - b[i]) > 48) n++;
  return n;
};

// Shorts: transcript words, cleanup, word-by-word captions, hooks, SRT and a captioned export.
async function shorts(page, scheme, dir) {
  const saved = () => page.waitForFunction(() => document.querySelector('.save')?.textContent === 'All changes saved');
  await page.goto(BASE + '/editor?mode=clip');
  await saved();
  const mon = page.getByRole('region', { name: 'Source monitor' });
  const prog = page.getByRole('region', { name: 'Program monitor' });
  const panel = page.getByRole('complementary', { name: 'Clip tools' });
  const length = async () => secs(await page.getByLabel('Sequence length').textContent());
  const undo = () => page.keyboard.press('ControlOrMeta+z');
  const near = (a, b, what) => assert.ok(Math.abs(a - b) < 0.07, `${what}: ${a} vs ${b}`);
  const goFrame = async (n) => {
    await prog.getByText('Program', { exact: true }).click();
    await page.keyboard.press('Home');
    for (let i = 0; i < Math.floor(n / 10); i++) await page.keyboard.press('Shift+ArrowRight');
    for (let i = 0; i < n % 10; i++) await page.keyboard.press('ArrowRight');
  };

  // Seed the transcript through the API (same origin), so no speech model is needed.
  const id = await page.evaluate(async (words) => {
    const list = await (await fetch('/api/editor/media')).json();
    const talk = list.find((m) => m.name === 'Talk.mp4');
    const put = await fetch(`/api/editor/media/${talk.id}/transcript`, {
      method: 'PUT',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ words }),
    });
    if (!put.ok) throw new Error(`transcript ${put.status}`);
    return talk.id;
  }, TALK_WORDS);
  assert.match(id, /^[0-9a-f]{32}$/);
  await page.reload();
  await saved();
  await newSequence(page);
  await loadSource(page);
  // The whole file, appended: its picture and sound sit on V1, which captions follow.
  await mon.getByText('Source', { exact: true }).click();
  await page.keyboard.press('Alt+x');
  await page.keyboard.press('Shift+.');
  near(await length(), 12, 'appended');
  await saved();

  // T opens the Transcript tab; clicking a word finds it in the source viewer.
  await page.locator('body').click({ position: { x: 5, y: 890 } });
  await page.keyboard.press('t');
  assert.equal(await panel.getByRole('tab', { name: 'Transcript' }).getAttribute('aria-selected'), 'true');
  const words = panel.getByRole('group', { name: 'Transcript words' }).getByRole('button');
  assert.equal(await words.count(), TALK_WORDS.length);
  await words.filter({ hasText: /^They$/ }).click();
  near(secs(await mon.getByLabel('Source playhead time').textContent()), 2.5, 'seek');
  // Shift-click selects a run; Delete cuts it (0.5 s) from the timeline in one undo step.
  await words.filter({ hasText: /^help\.$/ }).click({ modifiers: ['Shift'] });
  await page.keyboard.press('Delete');
  near(await length(), 11.5, 'words cut');
  await undo();
  near(await length(), 12, 'words restored');
  // Keyboard: arrows move along the words, Shift+arrow selects a run, F2 fixes the focused word, Escape keeps it.
  await words.filter({ hasText: /^They$/ }).click();
  await page.keyboard.press('Shift+ArrowRight');
  await page.keyboard.press('Shift+ArrowRight');
  assert.ok(await panel.getByRole('button', { name: 'Cut 3 words from the timeline' }).isEnabled());
  assert.equal(await page.evaluate(() => document.activeElement?.textContent), 'Extraordinarily');
  await page.keyboard.press('F2');
  const fix = panel.getByLabel('Fix the word');
  assert.equal(await fix.evaluate((el) => el === document.activeElement), true);
  assert.equal(await fix.inputValue(), 'Extraordinarily');
  await page.keyboard.press('Escape');
  assert.equal(await words.count(), TALK_WORDS.length);
  // The known filler "um" is listed; removing it cuts 0.3 s.
  const fillers = panel.getByRole('list', { name: 'Fillers' }).getByRole('listitem');
  await fillers.filter({ hasText: '“um”' }).getByRole('checkbox').check();
  await panel.getByRole('button', { name: 'Remove 1 filler' }).click();
  near(await length(), 11.7, 'filler cut');
  await undo();
  // Pauses over 0.6 s shrink to 0.25 s: 0.9, 1.8 and 1.1 s gaps lose 3.05 s together.
  await panel.getByRole('button', { name: 'Shorten pauses' }).click();
  near(await length(), 8.95, 'pauses');
  await undo();
  near(await length(), 12, 'pauses restored');
  await page.screenshot({ path: path.join(OUT, `shorts-transcript-${scheme}.png`) });

  // Captions follow the playhead page by page, matching the shared fixture.
  await panel.getByRole('tab', { name: 'Captions' }).click();
  await panel.getByRole('switch', { name: /Show captions/ }).check();
  await saved();
  // The fixture's page limits: three words and 16 letters.
  await panel.getByLabel('Words at once').fill(String(CAPTION_CASE.words_per_page));
  await panel.getByLabel('Words at once').press('Tab');
  await panel.getByLabel('Letters per line').fill(String(CAPTION_CASE.max_chars));
  await panel.getByLabel('Letters per line').press('Tab');
  await saved();
  for (const [t] of CAPTION_CASE.at) {
    const frame = Math.round(t * FPS);
    const at = frame / FPS;
    const page0 = CAPTION_CASE.pages.find((p) => p.t0 <= at && at < p.t1);
    await goFrame(frame);
    assert.equal(await page.locator('#caption-now').textContent(), page0 ? page0.text : '', `caption at ${at}`);
  }
  // A style change is one saved edit that survives a reload.
  await panel.getByRole('group', { name: 'Caption style' }).getByRole('button', { name: 'Karaoke' }).click();
  await saved();
  await page.reload();
  await saved();
  await panel.getByRole('tab', { name: 'Captions' }).click();
  const karaoke = panel.getByRole('group', { name: 'Caption style' }).getByRole('button', { name: 'Karaoke' });
  assert.equal(await karaoke.getAttribute('aria-pressed'), 'true');
  await panel.getByRole('group', { name: 'Caption style' }).getByRole('button', { name: 'Pop' }).click();
  await saved();
  const srt = await Promise.all([
    page.waitForEvent('download'),
    panel.getByRole('button', { name: 'Download SRT' }).click(),
  ]).then(([d]) => d);
  const srtPath = path.join(dir, `captions-${scheme}.srt`);
  await srt.saveAs(srtPath);
  const srtText = fs.readFileSync(srtPath, 'utf8');
  assert.match(srtText, /^1\r?\n00:00:00,000 --> 00:00:00,800\r?\nDid you know/);
  await goFrame(12);
  await page.waitForFunction(() => document.querySelector('#caption-now')?.textContent === 'Did you know');
  await page.waitForTimeout(300);
  await page.screenshot({ path: path.join(OUT, `shorts-captions-${scheme}.png`) });
  await prog.locator('canvas').screenshot({ path: path.join(OUT, `shorts-preview-frame-${scheme}.png`) });

  // Removing the track captions follow sends them back to the first track with sound, and the sequence still saves.
  const wordsFrom = panel.getByLabel('Words from');
  const trackOptions = () => wordsFrom.locator('option').evaluateAll((os) => os.map((o) => [o.value, o.textContent]));
  const before = new Set((await trackOptions()).map(([v]) => v));
  await page.getByTitle('Add an audio track').click();
  await saved();
  const [addedId, addedName] = (await trackOptions()).find(([v]) => !before.has(v));
  await wordsFrom.selectOption(addedId);
  await saved();
  const modes = page.getByRole('group', { name: 'Editor mode' });
  await modes.getByRole('button', { name: 'Edit', exact: true }).click();
  await page.getByRole('button', { name: addedName, exact: true }).click();
  await page.getByRole('button', { name: 'Remove track' }).click();
  await saved();
  await modes.getByRole('button', { name: 'Clip', exact: true }).click();
  await panel.getByRole('tab', { name: 'Captions' }).click();
  assert.equal(await panel.getByLabel('Words from').inputValue(), '');

  // Hooks: whole-sentence windows, ranked; Add appends one to the sequence.
  await panel.getByRole('tab', { name: 'Hooks' }).click();
  await panel.getByLabel('File').selectOption({ label: 'Talk.mp4' });
  await panel.getByLabel('Shortest (s)').fill('5');
  await panel.getByLabel('Longest (s)').fill('12');
  await panel.getByLabel('How many').fill('3');
  await panel.getByRole('button', { name: 'Find hooks' }).click();
  const hooks = panel.getByRole('list', { name: 'Hooks' }).getByRole('listitem');
  await hooks.first().waitFor();
  const found = await hooks.count();
  assert.ok(found >= 1 && found <= 3, `hooks ${found}`);
  await page.screenshot({ path: path.join(OUT, `shorts-hooks-${scheme}.png`) });
  await hooks.first().getByRole('button', { name: 'Add', exact: true }).click();
  assert.ok((await length()) > 12 + 4.9, `hook added: ${await length()}`);
  await undo();
  near(await length(), 12, 'hook undone');
  await saved();

  if (scheme === 'light') {
    // A captioned export: the still bars differ only where the caption is drawn.
    await page.getByRole('button', { name: 'Export', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: 'Export' });
    await dialog.getByLabel('Quality').selectOption('draft');
    assert.equal(await dialog.getByLabel('Burn in captions').isChecked(), true);
    await dialog.getByRole('button', { name: 'Export video' }).click();
    const link = dialog.getByRole('link', { name: /Download / });
    await link.waitFor({ timeout: 180000 });
    const download = await Promise.all([page.waitForEvent('download'), link.click()]).then(([d]) => d);
    const video = path.join(dir, 'captioned.mp4');
    await download.saveAs(video);
    const captioned = frameAt(video, 0.4);
    const plain = frameAt(video, 2.1);
    assert.ok(changed(captioned, plain) > 200, 'caption pixels at 0.4 s');
    assert.ok(changed(frameAt(video, 2.2), plain) < 50, 'no caption between pages');
    execFileSync(
      'ffmpeg',
      ['-y', '-v', 'error', '-ss', '0.4', '-i', video, '-frames:v', '1'].concat([
        path.join(OUT, 'shorts-export-frame.png'),
      ]),
    );
    await dialog.getByRole('button', { name: 'Close' }).click();

    // Without the speech engine, the Transcript tab explains the one-time setup.
    await page.route('**/api/editor/transcribe/status', async (route) => {
      const reply = await route.fetch();
      await route.fulfill({ response: reply, json: { ...(await reply.json()), installed: false } });
    });
    await page.reload();
    await saved();
    await panel.getByRole('tab', { name: 'Transcript' }).click();
    await panel.getByLabel('File').selectOption({ label: 'Interview take 1.mp4' });
    const note = panel.getByRole('note');
    await note.waitFor();
    assert.match(await note.textContent(), /scripts\/setup_speech_model\.sh/);
    assert.match(await note.textContent(), /CC-BY-4\.0/);
    await page.screenshot({ path: path.join(OUT, 'shorts-setup.png') });
    await page.unroute('**/api/editor/transcribe/status');
  }
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'editor-fixture-'));
  const media = fixture(dir);
  const talk = talkFixture(dir);
  const browser = await chromium.launch({ headless: true });
  const errors = [];
  try {
    for (const scheme of ['light', 'dark']) {
      const context = await browser.newContext({
        viewport: { width: 1440, height: 900 },
        colorScheme: scheme,
        acceptDownloads: true,
      });
      const page = await context.newPage();
      page.on('pageerror', (error) => errors.push(error.message));
      page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
      await page.goto(BASE + '/editor');
      await page.waitForFunction(() => document.querySelector('.save')?.textContent === 'All changes saved');

      // The tab sits in the app's main menu.
      assert.equal(await page.locator('.appnav a[aria-current=page]').textContent(), 'Editor');

      if (scheme === 'light') {
        await page.screenshot({ path: path.join(OUT, 'empty.png') });
        // Import through the bin, wait for the preview to be prepared, then add it at the playhead.
        await page.locator('.bin input[type=file]').setInputFiles(media);
        await page.getByText('Interview take 1.mp4', { exact: true }).waitFor();
        await page.waitForFunction(() => document.querySelector('.bin .meta')?.textContent?.includes('640×360'), null, {
          timeout: 60000,
        });
        await page.getByRole('button', { name: 'Add Interview take 1.mp4 at the playhead' }).click();
        // A video clip carries its own sound on V1 until its audio is detached.
        await clips(page).first().waitFor();
        assert.match(
          (await clips(page).first().getAttribute('aria-label')) ?? '',
          /on V1, starts 00:00:00:00, 6\.00 seconds/,
        );
        await page.getByRole('menuitem', { name: 'Clip' }).click();
        await page.getByRole('menuitem', { name: 'Detach audio' }).click();
        assert.equal(await clips(page).count(), 2);
        await page.waitForFunction(() => document.querySelector('.save')?.textContent === 'All changes saved');

        // Split everything at 2 s with the shortcut, then undo and redo it.
        await page.locator('[data-ruler]').focus();
        for (let i = 0; i < 60; i++) await page.keyboard.press('ArrowRight');
        await page.locator('body').click({ position: { x: 5, y: 890 } });
        // With nothing selected, the split cuts every track under the playhead.
        await page.keyboard.press('Escape');
        await page.keyboard.press(process.platform === 'darwin' ? 'Meta+k' : 'Control+k');
        assert.equal(await clips(page).count(), 4);
        await page.keyboard.press(process.platform === 'darwin' ? 'Meta+z' : 'Control+z');
        assert.equal(await clips(page).count(), 2);
        await page.keyboard.press(process.platform === 'darwin' ? 'Meta+Shift+z' : 'Control+y');
        assert.equal(await clips(page).count(), 4);

        // Select the second V1 piece and give it a dissolve and half speed from the inspector.
        await clips(page).filter({ hasText: 'Interview' }).nth(1).click();
        await page.getByRole('heading', { name: 'Clip' }).waitFor();
        await page.getByLabel('Transition from previous clip').selectOption('dissolve');
        await page.getByLabel('Speed').selectOption('0.5');
        assert.match((await clips(page).nth(1).getAttribute('aria-label')) ?? '', /0\.5× speed, dissolve in/);

        // Mark in and out, add a marker, then keyboard-drive the menu bar.
        await page.locator('body').click({ position: { x: 5, y: 890 } });
        await page.keyboard.press('Home');
        await page.keyboard.press('i');
        for (let i = 0; i < 30; i++) await page.keyboard.press('ArrowRight');
        await page.keyboard.press('m');
        await page.keyboard.press('End');
        await page.keyboard.press('o');
        await page.getByRole('menuitem', { name: 'File' }).focus();
        await page.keyboard.press('Enter');
        assert.equal(
          await page.evaluate(() => document.activeElement?.textContent?.trim().startsWith('New sequence')),
          true,
        );
        await page.keyboard.press('Escape');
        assert.equal(await page.locator('[role=menu]').count(), 0);

        // Export the in/out range as a draft MP4 and check the download plays as video.
        await page.waitForFunction(() => document.querySelector('.save')?.textContent === 'All changes saved');
        await page.getByRole('button', { name: 'Export', exact: true }).click();
        await page.getByLabel('Quality').selectOption('draft');
        assert.equal(await page.getByLabel(/In to out/).isChecked(), true);
        await page.getByRole('button', { name: 'Export video' }).click();
        const link = page.getByRole('link', { name: /Download / });
        await link.waitFor({ timeout: 120000 });
        const download = await Promise.all([page.waitForEvent('download'), link.click()]).then(([d]) => d);
        const video = path.join(dir, 'out.mp4');
        await download.saveAs(video);
        const report = execFileSync('ffmpeg', ['-hide_banner', '-i', video, '-f', 'null', '-'], {
          encoding: 'utf8',
          stdio: ['ignore', 'pipe', 'pipe'],
        });
        assert.ok(report !== undefined);
        const xml = await Promise.all([
          page.waitForEvent('download'),
          page.getByRole('button', { name: 'Premiere Pro XML' }).click(),
        ]).then(([d]) => d);
        const xmlPath = path.join(dir, 'cut.xml');
        await xml.saveAs(xmlPath);
        const text = fs.readFileSync(xmlPath, 'utf8');
        assert.match(text, /<!DOCTYPE xmeml>/);
        assert.match(text, /Cross Dissolve/);
        await page.screenshot({ path: path.join(OUT, 'export.png') });
        await page.getByRole('button', { name: 'Close' }).first().click();
      } else {
        // Reloaded in dark mode: the saved sequence and media come back.
        await clips(page).first().waitFor();
        assert.equal(await clips(page).count(), 4);
        await timelineGestures(page);
      }
      // The timeline scrolls inside its panel; the page itself never scrolls sideways.
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
      await page.screenshot({ path: path.join(OUT, `${scheme}.png`) });
      await context.close();
    }
    for (const scheme of ['light', 'dark']) {
      const context = await browser.newContext({
        viewport: { width: 1440, height: 900 },
        colorScheme: scheme,
        acceptDownloads: true,
      });
      const page = await context.newPage();
      page.on('pageerror', (error) => errors.push(error.message));
      page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
      await clipMode(page, scheme, talk, dir);
      await shorts(page, scheme, dir);
      await context.close();
    }
    assert.deepEqual(errors, []);
    console.log('editor browser check passed');
  } finally {
    await browser.close();
    fs.rmSync(dir, { recursive: true, force: true });
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
