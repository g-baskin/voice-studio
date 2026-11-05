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
