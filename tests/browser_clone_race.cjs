// The cloning page must select the new voice before it says "Created ... Preview it below".
// Server answers are simulated, so this runs in seconds without the cloning engine and is not load-sensitive.
const { launch } = require('./browser_support.cjs');
const assert = require('node:assert/strict');
const base = process.env.NV_URL;
if (!base) throw new Error('Run through npm run test:browser.');

const CLONE = {
  id: 'clone:0123456789ab',
  name: 'Race Check',
  kind: 'clone',
  gender: 'unknown',
  language: 'English',
  lang: 'en-us',
  starred: false,
};
const STOCK = {
  id: 'af_heart',
  name: 'Heart',
  kind: 'stock',
  gender: 'female',
  language: 'American English',
  lang: 'en-us',
  starred: false,
};

(async () => {
  const browser = await launch({ headless: true });
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));
    let created = false;
    await page.route('**/api/clone/status', (route) =>
      route.fulfill({
        json: {
          installed: true,
          model: 'Mock',
          license: 'MIT',
          sample_rate: 24000,
          device: 'cpu',
          warm: true,
          emotion_tags: [],
          languages: [{ code: 'en', name: 'English' }],
        },
      }),
    );
    await page.route('**/api/clone/voices', (route) => {
      created = true;
      return route.fulfill({ json: { ...CLONE, meta: { reference_seconds: 8 } } });
    });
    // A slow voice list is what exposed the race: the message used to appear before the list reloaded.
    await page.route('**/api/voices', async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 1500));
      await route.fulfill({ json: { voices: [], catalog: created ? [STOCK, CLONE] : [STOCK] } });
    });

    await page.goto(base + '/voice-lab');
    if (await page.$('#tab-clone')) await page.click('#tab-clone');
    await page.waitForFunction(() => /Engine: Mock/.test(document.querySelector('#clonePanel')?.textContent ?? ''));
    await page.setInputFiles('#cloneFile', {
      name: 'reference.wav',
      mimeType: 'audio/wav',
      buffer: Buffer.from('RIFF'),
    });
    await page.fill('#cloneName', 'Race Check');
    await page.check('#cloneConsent');
    await page.click('#cloneCreate');
    await page.waitForFunction(
      () => /Created/.test(document.querySelector('#cloneCreateMsg')?.textContent ?? ''),
      null,
      {
        timeout: 15000,
      },
    );
    // Read immediately: the moment "Created" shows, the new voice must already be selected.
    assert.equal(await page.inputValue('#cloneVoice'), CLONE.id);
    assert.equal(await page.isDisabled('#clonePreview'), false);
    assert.deepEqual(errors, []);
    console.log('Clone race passed: the new voice is selected before "Created" appears, even with a slow voice list.');
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
