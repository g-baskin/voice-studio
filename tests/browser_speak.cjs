const { launch } = require('./browser_support.cjs');
const assert = require('node:assert/strict');
const base = process.env.NV_URL;
if (!base || !process.env.NATURALVOICE_DATA) throw new Error('Run through npm run test:browser.');
(async () => {
  const browser = await launch({ headless: true });
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto(base + '/speak');
    assert.equal(await page.title(), 'Speak · Shark Audio');
    assert.equal(await page.getAttribute('a[href="/speak"]', 'aria-current'), 'page');
    await page.waitForSelector('select[aria-label="Voice for Mara"] option', { state: 'attached' });
    assert.equal((await page.$$('.cast select')).length, 4, 'one voice per speaker plus narration');

    await page.fill('#script', 'Mara: [whisper] Did you hear that?\nJonah: [excited] They made it back!');
    await page.getByRole('button', { name: 'Perform', exact: true }).click();
    await page.waitForFunction(() => document.querySelectorAll('.chunk[data-state="ready"]').length === 2, null, {
      timeout: 120000,
    });
    const readouts = await page.$$eval('.readout li', (els) => els.map((e) => e.textContent?.trim() ?? ''));
    assert.ok(
      readouts.some((t) => t.startsWith('[whisper] Approximated')),
      readouts.join('|'),
    );
    assert.ok(
      readouts.some((t) => t.startsWith('[excited] Applied')),
      readouts.join('|'),
    );

    const first = page.locator('.chunk').first();
    await first.locator('input[type=text]').fill('much slower');
    await first.getByRole('button', { name: 'Revise' }).click();
    await first.locator('button[aria-pressed="true"]', { hasText: 'much slower' }).waitFor({ timeout: 60000 });
    assert.match((await first.locator('.status').textContent()) ?? '', /Understood: much slower/);
    await first.getByRole('button', { name: 'Retake' }).click();
    await first.locator('button[aria-pressed="true"]', { hasText: 'retake' }).waitFor({ timeout: 60000 });
    assert.equal(await first.locator('[role=group][aria-label=Versions] button').count(), 3);

    const download = page.getByRole('link', { name: 'Download performance' });
    const wav = await page.request.get(base + (await download.getAttribute('href')));
    assert.equal(wav.status(), 200);
    assert.equal((await wav.body()).subarray(0, 4).toString(), 'RIFF');

    await first.locator('input[type=text]').fill('zebra');
    await first.getByRole('button', { name: 'Revise' }).click();
    await page.waitForFunction(() => /recognise/.test(document.querySelector('.chunk .status')?.textContent ?? ''));

    // Repeating a tag in one chunk must not break the readout list.
    await page.fill('#script', 'Hello [sparkle] there [sparkle] friend.');
    await page.getByRole('button', { name: 'Perform', exact: true }).click();
    await page.waitForFunction(
      () =>
        document.querySelectorAll('.chunk').length === 1 &&
        document.querySelector('.chunk')?.getAttribute('data-state') === 'ready',
      null,
      { timeout: 120000 },
    );
    const repeated = await page.$$eval('.readout li', (els) => els.map((e) => e.textContent?.trim() ?? ''));
    assert.deepEqual(repeated.filter((t) => t.startsWith('[sparkle] Not recognised')).length, 2, repeated.join('|'));

    await page.setViewportSize({ width: 390, height: 844 });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= 390), 'no horizontal overflow');
    assert.deepEqual(errors, []);
    console.log(
      'Speak browser passed: cast, directions, honest readouts, chunked perform, revise, retake, download, error, mobile.',
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
