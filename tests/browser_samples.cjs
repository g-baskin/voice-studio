// Run only against a server with disposable NATURALVOICE_DATA. Writes synthetic media.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const BASE = process.env.NV_URL || 'http://127.0.0.1:8773';
const OUT = process.env.NV_SCREENSHOTS || '/tmp/voice-sample-browser';

function wav() {
  const rate = 16000;
  const count = rate * 8;
  const out = Buffer.alloc(44 + count * 2);
  out.write('RIFF', 0);
  out.writeUInt32LE(out.length - 8, 4);
  out.write('WAVEfmt ', 8);
  out.writeUInt32LE(16, 16);
  out.writeUInt16LE(1, 20);
  out.writeUInt16LE(1, 22);
  out.writeUInt32LE(rate, 24);
  out.writeUInt32LE(rate * 2, 28);
  out.writeUInt16LE(2, 32);
  out.writeUInt16LE(16, 34);
  out.write('data', 36);
  out.writeUInt32LE(count * 2, 40);
  for (let i = 0; i < count; i++)
    out.writeInt16LE(Math.round(7000 * Math.sin((i / rate) * 2 * Math.PI * 160)), 44 + i * 2);
  return out;
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const errors = [];
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto(BASE + '/samples.html');
    await page.waitForFunction(() => document.getElementById('status').textContent.includes('engine ready'));
    await page.screenshot({ path: path.join(OUT, 'desktop-empty.png'), fullPage: true });
    // Keyboard reaches the skip link and the main content without a pointer.
    await page.keyboard.press('Tab');
    assert.equal(await page.evaluate(() => document.activeElement.textContent), 'Skip to sample collections');
    await page.keyboard.press('Enter');
    assert.equal(await page.evaluate(() => document.activeElement.id), 'main');
    await page.locator('#personName').fill('Browser fixture <speaker>');
    await page.locator('#personForm input[type=checkbox]').check();
    await page.getByRole('button', { name: 'Create collection', exact: true }).click();
    await page.waitForFunction(
      () => /** @type {HTMLSelectElement} */ (document.getElementById('personSelect')).value !== '',
    );
    await page
      .locator('#mediaFile')
      .setInputFiles({ name: 'Synthetic test.wav', mimeType: 'audio/wav', buffer: wav() });
    await page.locator('#importForm input[name=consent]').check();
    await page.getByRole('button', { name: 'Import and detect speakers', exact: true }).click();
    await page.locator('#review').waitFor({ state: 'visible', timeout: 180000 });
    await page.locator('#sampleStart').fill('0');
    await page.locator('#sampleEnd').fill('1');
    await page.getByRole('button', { name: 'Listen to selection', exact: true }).click();
    await page.waitForFunction(() => {
      const selection = /** @type {HTMLAudioElement} */ (document.getElementById('selectionAudio'));
      return selection.paused && selection.currentTime >= 1;
    });
    await page.evaluate(async () => {
      const original = /** @type {HTMLAudioElement} */ (document.getElementById('originalAudio'));
      original.muted = true;
      original.currentTime = 2;
      await original.play();
    });
    await page.waitForFunction(
      () => /** @type {HTMLAudioElement} */ (document.getElementById('originalAudio')).currentTime > 2.3,
    );
    await page.evaluate(() => /** @type {HTMLAudioElement} */ (document.getElementById('originalAudio')).pause());
    await page.locator('#sampleEnd').fill('6');
    await page.locator('#sampleConsent').check();
    await page.getByRole('button', { name: 'Save approved sample', exact: true }).click();
    await page.locator('#samples input[type=checkbox]').waitFor();
    await page.locator('#samples input[type=checkbox]').check();
    await page.getByRole('button', { name: 'Build reference version', exact: true }).click();
    await page.locator('#versions strong').waitFor();
    assert.match(await page.locator('#versions').textContent(), /Browser fixture <speaker> v1/);
    assert.equal(await page.locator('speaker').count(), 0);
    await page.getByRole('button', { name: 'Mark preferred', exact: true }).click();
    await page.waitForFunction(() => document.getElementById('versions').textContent.includes('(preferred)'));
    await page.reload();
    await page.locator('#personSelect').selectOption({ label: 'Browser fixture <speaker>' });
    await page.waitForFunction(() => document.getElementById('versions').textContent.includes('(preferred)'));
    // Server validation preserves the edited values and reports the error.
    await page.locator('#sourceSelect').selectOption({ label: 'Synthetic test.wav' });
    await page.locator('#review').waitFor({ state: 'visible' });
    await page.locator('#sampleEnd').fill('9');
    await page.locator('#sampleConsent').check();
    await page.getByRole('button', { name: 'Save approved sample', exact: true }).click();
    await page.waitForFunction(() => document.getElementById('status').classList.contains('error'));
    assert.equal(await page.locator('#sampleEnd').inputValue(), '9');
    await page.locator('#sampleEnd').fill('6');
    await page.screenshot({ path: path.join(OUT, 'desktop-review.png'), fullPage: true });
    for (const width of [390, 320]) {
      await page.setViewportSize({ width, height: 900 });
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
      await page.screenshot({ path: path.join(OUT, `mobile-${width}.png`), fullPage: true });
    }
    await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' });
    await page.screenshot({ path: path.join(OUT, 'dark-mobile.png'), fullPage: true });
    await page.emulateMedia({ forcedColors: 'active' });
    assert.ok(await page.locator('#saveSample').isVisible());
    assert.deepEqual(errors, []);
    console.log(
      'Browser sample flow passed: import, review, save, version, preference, refresh, error, keyboard, reflow.',
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
