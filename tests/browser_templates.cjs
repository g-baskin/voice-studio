// Optional real-browser smoke test. Set PLAYWRIGHT_MODULE if Playwright is supplied by GG Coder.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');

(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto('http://127.0.0.1:8765');
    await page.waitForSelector('#template:not([disabled])');
    const keys = ['ai_clean', 'dereverb', 'demetal', 'deharsh', 'warmth', 'denoise', 'room_tone'];
    const templates = {
      clean: [0, 0, 0.25, 0.2, 0.25, 0, 0],
      ad: [1, 0.3, 0.7, 0.6, 0.5, 0, 0],
      metallic: [0, 0, 0.85, 0.4, 0.35, 0, 0],
      echo: [1, 0.6, 0.4, 0.3, 0.25, 0, 0],
      noise: [1, 0, 0.25, 0.2, 0.25, 0.2, 0],
      strong: [1, 0.6, 1, 0.9, 0.7, 0, 0],
    };
    for (const [name, values] of Object.entries(templates)) {
      await page.selectOption('#template', name);
      for (let i = 0; i < keys.length; i++) {
        assert.equal(Number(await page.inputValue(`#s-${keys[i]}`)), values[i]);
        assert.equal(await page.textContent(`#v-${keys[i]}`), `${Math.round(values[i] * 100)}%`);
      }
    }
    await page.selectOption('#template', 'clean');
    await page.focus('#s-room_tone');
    await page.keyboard.press('ArrowRight');
    assert.equal(Number(await page.inputValue('#s-room_tone')), 0.05);
    assert.match(await page.textContent('#templateState'), /Custom settings/);
    await page.click('#resetTemplate');
    assert.equal(Number(await page.inputValue('#s-room_tone')), 0);
    // A real user click must request the native file chooser.
    const chooserPromise = page.waitForEvent('filechooser');
    await page.click('#drop');
    const chooser = await chooserPromise;
    await chooser.setFiles({ name: 'template-test.wav', mimeType: 'audio/wav', buffer: Buffer.from('test') });
    assert.equal(await page.textContent('#fileName'), 'template-test.wav');
    assert.equal(await page.isEnabled('#cleanBtn'), true);
    // Verify the browser sends the current controls, without processing a fake recording.
    let payload;
    await page.route('**/api/clean', async (route) => {
      payload = route.request().postData();
      await route.fulfill({
        status: 400,
        contentType: 'application/json',
        body: '{"detail":"Test upload intercepted"}',
      });
    });
    await page.click('#cleanBtn');
    await page.waitForFunction(() => document.querySelector('#cleanStatus').textContent === 'Test upload intercepted');
    assert.match(payload, /name="room_tone"\r\n\r\n0\r\n/);
    assert.match(payload, /name="demetal"\r\n\r\n0.25\r\n/);
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    await page.selectOption('#template', 'echo');
    assert.equal(Number(await page.inputValue('#s-dereverb')), 0.6);
    assert.deepEqual(errors, []);
    console.log(
      'Browser passed: all six templates, labels, keyboard adjustment, reset, native chooser event, upload values, mobile width, no script errors.',
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
