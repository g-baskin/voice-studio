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

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'editor-fixture-'));
  const media = fixture(dir);
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
