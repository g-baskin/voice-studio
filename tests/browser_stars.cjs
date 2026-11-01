// Star a voice in Voice Lab; check ordering, filter, persistence, Studio + Clean pickers. Cleans up after itself.
const chromium = require('./browser_support.cjs');
const assert = require('node:assert/strict');
const BASE = process.env.NV_URL || 'http://127.0.0.1:8765';
(async () => {
  const browser = await chromium.launch({ headless: true });
  const errors = [];
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    page.on('pageerror', (e) => errors.push(e.message));
    await page.goto(BASE + '/voicelab.html');
    await page.waitForSelector('#libList li');
    await page.fill('#libSearch', 'bella');
    const star = page.getByRole('button', { name: 'Star Bella' });
    assert.equal(await star.getAttribute('aria-pressed'), 'false');
    await star.click();
    // The row re-renders; focus returns to the same star so keyboard users keep their place.
    await page.waitForSelector('button[aria-label="Star Bella"][aria-pressed="true"]');
    const again = page.getByRole('button', { name: 'Star Bella' });
    assert.equal(await again.getAttribute('aria-pressed'), 'true');
    assert.equal(await again.evaluate((b) => document.activeElement === b), true);
    await page.fill('#libSearch', '');
    assert.match(await page.locator('#libList li').first().textContent(), /Bella/, 'starred voice floats to the top');
    await page.selectOption('#libKind', 'starred');
    assert.equal(await page.locator('#libList li').count(), 1);
    // Persistence across reload (stored on the server, not just in this browser tab).
    await page.reload();
    await page.waitForSelector('#libList li');
    await page.selectOption('#libKind', 'starred');
    assert.match(await page.locator('#libList li').first().textContent(), /Bella/);
    // Keyboard: Space toggles the star.
    await page.getByRole('button', { name: 'Star Bella' }).focus();
    await page.keyboard.press('Space');
    await page.waitForFunction(() => document.querySelectorAll('#libList li').length === 0);
    assert.match(await page.textContent('#libStatus'), /No starred voices yet/);
    await page.selectOption('#libKind', '');
    await page.fill('#libSearch', 'bella');
    await page.getByRole('button', { name: 'Star Bella' }).click();
    await page.waitForSelector('button[aria-label="Star Bella"][aria-pressed="true"]');
    // Studio picker lists starred voices first.
    const studio = await browser.newPage();
    studio.on('pageerror', (e) => errors.push(e.message));
    await studio.goto(BASE + '/studio.html');
    await studio.waitForSelector('.line select, select[aria-label*="oice"]');
    const labels = await studio.$$eval('optgroup', (gs) => gs.map((g) => g.label));
    assert.ok(
      labels.some((l) => l.includes('Starred')),
      'Studio shows a Starred group: ' + labels.join('|'),
    );
    // Clean page quick voice picker too.
    const clean = await browser.newPage();
    clean.on('pageerror', (e) => errors.push(e.message));
    await clean.goto(BASE + '/index.html');
    await clean.waitForFunction(() => document.querySelector('#voice optgroup'));
    assert.equal(await clean.$eval('#voice optgroup', (g) => g.label), '\u2605 Starred');
    // Mobile width.
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    await page.fill('#libSearch', 'bella');
    await page.screenshot({
      path: require('node:path').join(process.env.NV_SCREENSHOTS || require('node:os').tmpdir(), 'nv-stars-mobile.png'),
    });
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.selectOption('#libKind', 'starred');
    await page.fill('#libSearch', '');
    await page.screenshot({
      path: require('node:path').join(
        process.env.NV_SCREENSHOTS || require('node:os').tmpdir(),
        'nv-stars-desktop.png',
      ),
    });
    // Clean up: unstar.
    await page.getByRole('button', { name: 'Star Bella' }).click();
    await page.waitForFunction(() => document.querySelectorAll('#libList li').length === 0);
    assert.deepEqual(errors, []);
    console.log('stars browser check passed');
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
