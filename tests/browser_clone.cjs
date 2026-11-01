// Browser check for the cloning panel. Needs a server on 127.0.0.1:8773 and NV_REF (a 5-60 s WAV, default /tmp/nv_ref8.wav).
// PLAYWRIGHT_MODULE='/Applications/GG Coder.app/Contents/Resources/sidecar/node_modules/playwright' node tests/browser_clone.cjs
const chromium = require('./browser_support.cjs');
const BASE = (process.env.NV_URL || 'http://127.0.0.1:8773') + '/';
const REF = process.env.NV_REF || '/tmp/nv_ref8.wav';
const HARNESS = `<!doctype html><html><head><meta charset="utf-8"><base href="${BASE}">
<meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="${BASE}app.css"></head>
<body><main class="page"><h1>Voice Lab</h1><section id="clonePanel"></section></main><script src="${BASE}clone.js"></script></body></html>`;
const ok = (c, m) => {
  if (!c) throw new Error('FAIL: ' + m);
  console.log('ok -', m);
};

(async () => {
  const browser = await chromium.launch();
  const errors = [];
  const open = async (opts) => {
    const page = await browser.newPage(opts);
    page.on('pageerror', (e) => errors.push(e.message));
    const has = (await page.request.get(BASE + 'voice-lab')).ok();
    if (has) {
      await page.goto(BASE + 'voice-lab');
      if (await page.$('#tab-clone')) await page.click('#tab-clone');
    } else {
      await page.goto(BASE + 'manifest.webmanifest');
      await page.setContent(HARNESS, { waitUntil: 'load' });
    }
    await page.waitForSelector('#cloneCreate');
    await page.waitForFunction(() => !/Checking/.test(document.querySelector('#clonePanel .status').textContent));
    return page;
  };
  try {
    const page = await open({ viewport: { width: 1200, height: 900 } });
    ok(
      /Chatterbox/.test(await page.textContent('#clonePanel')),
      'engine status shown: ' + (await page.textContent('#clonePanel .card')).slice(0, 120),
    );
    await page.setInputFiles('#cloneFile', REF);
    await page.fill('#cloneName', 'Browser Mike');
    ok(await page.isDisabled('#cloneCreate'), 'create disabled without consent');
    ok(/consent/.test(await page.textContent('#cloneWhy')), 'explains consent is missing');
    await page.focus('#cloneConsent');
    await page.keyboard.press('Space');
    ok(!(await page.isDisabled('#cloneCreate')), 'consent via keyboard enables create');
    await page.click('#cloneCreate');
    await page.waitForFunction(
      () =>
        /Created|error/i.test(
          document.querySelector('#cloneCreateMsg').textContent + document.querySelector('#cloneCreateMsg').className,
        ),
      null,
      { timeout: 30000 },
    );
    ok(
      /Created/.test(await page.textContent('#cloneCreateMsg')),
      'clone created: ' + (await page.textContent('#cloneCreateMsg')),
    );
    ok((await page.inputValue('#cloneVoice')).startsWith('clone:'), 'new voice selected for preview');
    await page.fill('#clonePreviewText', 'Nice to meet you.');
    await page.click('#clonePreview');
    await page.waitForFunction(
      () =>
        /Done|error/i.test(
          document.querySelector('#clonePreviewMsg').textContent + document.querySelector('#clonePreviewMsg').className,
        ),
      null,
      { timeout: 120000 },
    );
    ok(
      /Done/.test(await page.textContent('#clonePreviewMsg')),
      'preview: ' + (await page.textContent('#clonePreviewMsg')),
    );
    const dur = await page.$eval(
      '#clonePlayer',
      (a) =>
        new Promise((r) =>
          a.readyState >= 1 ? r(a.duration) : a.addEventListener('loadedmetadata', () => r(a.duration)),
        ),
    );
    ok(dur > 0.5, `audio loads (${dur.toFixed(2)} s)`);
    // voice changer: performance = Kokoro af_heart clip (NV_PERF), target = the clone just made
    ok(await page.isDisabled('#vcConvert'), 'convert disabled before performance/consent');
    await page.setInputFiles('#vcFile', process.env.NV_PERF || '/tmp/src24.wav');
    ok(/rights/.test(await page.textContent('#vcWhy')), 'voice changer asks for rights consent');
    await page.check('#vcConsent');
    await page.click('#vcConvert');
    await page.waitForFunction(
      () =>
        /Done|error/i.test(document.querySelector('#vcMsg').textContent + document.querySelector('#vcMsg').className),
      null,
      { timeout: 120000 },
    );
    ok(/Done/.test(await page.textContent('#vcMsg')), 'convert: ' + (await page.textContent('#vcMsg')));
    ok(
      (await page.isVisible('#vcOriginal')) && (await page.isVisible('#vcConverted')),
      'original and converted players shown',
    );
    await page.screenshot({
      path: require('node:path').join(
        process.env.NV_SCREENSHOTS || require('node:os').tmpdir(),
        'nv-clone-desktop.png',
      ),
      fullPage: true,
    });

    const m = await open({ viewport: { width: 390, height: 844 }, isMobile: true });
    const over = await m.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    ok(over <= 0, `no horizontal overflow at 390 px (${over})`);
    await m.click('#clonePanel [role=tab]:nth-child(2)');
    ok(await m.isVisible('#clonePaneRecord .script'), 'record tab shows script');
    await m.screenshot({
      path: require('node:path').join(process.env.NV_SCREENSHOTS || require('node:os').tmpdir(), 'nv-clone-mobile.png'),
      fullPage: true,
    });
    ok(errors.length === 0, 'no page errors ' + errors.join('; '));
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e.message);
  process.exit(1);
});
