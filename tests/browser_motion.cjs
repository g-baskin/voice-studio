// Read-only motion regression checks against actual HTML/CSS. No server, models or application scripts.
const chromium = require('./browser_support.cjs');
const assert = require('node:assert/strict');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({ javaScriptEnabled: false, serviceWorkers: 'block' });
    const page = await context.newPage();
    const open = (file) => page.goto(pathToFileURL(path.resolve(__dirname, '../src/naturalvoice/web', file)).href);
    const cases = [
      ['index.html', '.drop', '0.15s', '--motion-fast'],
      ['index.html', '.progress div', '0.3s', '--motion-progress'],
      ['studio.html', '.progress div', '0.3s', '--motion-progress'],
      ['voicelab.html', '.bar span', '0.3s', '--motion-progress'],
    ];
    for (const [file, selector, duration, token] of cases) {
      await page.emulateMedia({ reducedMotion: 'no-preference' });
      await open(file);
      const target = page.locator(selector).first();
      const style = () =>
        target.evaluate((element) => ({
          duration: getComputedStyle(element).transitionDuration,
          easing: getComputedStyle(element).transitionTimingFunction,
        }));
      assert.deepEqual(await style(), { duration, easing: 'ease' }, `${file}: original timing retained`);
      await page.evaluate((name) => {
        document.documentElement.style.setProperty(name, '420ms');
        document.documentElement.style.setProperty('--motion-easing', 'linear');
      }, token);
      assert.deepEqual(
        await style(),
        { duration: '0.42s', easing: 'linear' },
        `${file}: shared settings control motion`,
      );
      await page.emulateMedia({ reducedMotion: 'reduce' });
      assert.equal((await style()).duration, '0s', `${file}: reduced motion wins over token overrides`);
    }

    await open('samples.html');
    const native = page.locator('#importProgress progress');
    const fallback = page.locator('#importProgress .static-status');
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 900 });
      for (const mode of ['no-preference', 'reduce']) {
        await page.emulateMedia({ reducedMotion: /** @type {'reduce' | 'no-preference'} */ (mode) });
        // The existing source-loading code toggles this container for running/completed work.
        await page.locator('#importProgress').evaluate((element) => {
          element.hidden = true;
        });
        assert.equal(await native.isVisible(), false);
        assert.equal(await fallback.isVisible(), false);
        await page.locator('#importProgress').evaluate((element) => {
          element.hidden = false;
        });
        assert.equal(await native.isVisible(), mode === 'no-preference');
        assert.equal(await fallback.isVisible(), mode === 'reduce');
        assert.equal(await page.locator('#sourceStatus').getAttribute('role'), 'status');
        if (mode === 'reduce') {
          assert.equal(await fallback.textContent(), 'Analyzing recording...');
          assert.equal(await fallback.evaluate((element) => element.getAnimations().length), 0);
          const first = await fallback.screenshot();
          await page.waitForTimeout(240);
          const second = await fallback.screenshot();
          assert.ok(first.equals(second), 'Reduced-motion loading indicator must remain visually static');
        }
      }
    }
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    assert.equal(await native.isVisible(), true, 'Changing the preference restores native progress');
    assert.equal(await fallback.isVisible(), false);
    console.log(
      'Motion checks passed: four shared transitions, reduced-motion override, static loading feedback, preference changes and desktop/mobile states.',
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
