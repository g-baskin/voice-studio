// Real-browser check of the Studio page. Needs a running server:
//   uv run voicestudio serve --port 8772
//   PLAYWRIGHT_MODULE=... node tests/browser_studio.cjs
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const errors = [];
const consoleText = [];
const BASE = process.env.NV_URL || 'http://127.0.0.1:8772';

(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--autoplay-policy=no-user-gesture-required'] });
  try {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, acceptDownloads: true });
    const page = await ctx.newPage();
    page.on('pageerror', (e) => errors.push(e.message));
    page.on('console', (m) => consoleText.push(m.text()));
    await page.goto(BASE + '/studio.html');
    await page.evaluate(() => localStorage.clear());
    await page.reload();
    await page.waitForSelector('#lines textarea');
    assert.equal(await page.getAttribute('a[href="studio.html"]', 'aria-current'), 'page');

    // 3 lines, 2 voices
    await page.click('#add');
    await page.click('#add');
    const texts = ['Welcome to the show.', 'Thanks for having me.', 'Let us begin.'];
    const voices = ['af_heart', 'am_michael', 'af_heart'];
    const speakers = ['Host', 'Guest', 'Host'];
    for (let i = 0; i < 3; i++) {
      await page.fill(`[aria-label="Line ${i + 1}"] textarea`, texts[i]);
      await page.selectOption(`[aria-label="Line ${i + 1} voice"]`, voices[i]);
      await page.fill(`[aria-label="Line ${i + 1} speaker"]`, speakers[i]);
    }
    await page.selectOption('[aria-label="Line 2 delivery"]', 'warm');
    await page.fill('#title', 'Browser test');

    // keyboard reorder round-trip
    await page.focus('[aria-label="Line 3"] textarea');
    await page.keyboard.press('Alt+ArrowUp');
    assert.equal(await page.inputValue('[aria-label="Line 2"] textarea'), texts[2]);
    await page.keyboard.press('Alt+ArrowDown');
    assert.equal(await page.inputValue('[aria-label="Line 3"] textarea'), texts[2]);

    // preview
    await page.click('[aria-label="Preview line 1"]');
    await page.waitForSelector('[aria-label="Line 1"] audio:not([hidden])', { timeout: 60000 });

    // alternate take on line 2, then use it
    await page.click('[aria-label="New take for line 2"]');
    await page.waitForSelector('[aria-label="Use take 2 for line 2"]');
    await page.waitForSelector('[aria-label="Line 2"] audio:not([hidden])', { timeout: 60000 });
    await page.check('[aria-label="Use take 2 for line 2"]');

    // ACX switches to 44.1 kHz MP3 + room tone; back to podcast
    await page.selectOption('#target', 'acx');
    assert.equal(await page.inputValue('#rate'), '44100');
    assert.equal(await page.inputValue('#format'), 'mp3');
    assert.ok(await page.isChecked('#roomtone'));
    await page.selectOption('#target', 'podcast');
    await page.selectOption('#rate', '24000');
    await page.selectOption('#format', 'wav');

    // fit to a custom length
    await page.selectOption('#fit', 'custom');
    await page.fill('#fit-custom', '6');

    // render (keyboard shortcut)
    await page.selectOption('#target', 'podcast');
    await page.check('#stems');
    await page.check('#captions');
    await page.keyboard.press('Control+Shift+Enter');
    await page.waitForSelector('#result:not([hidden])', { timeout: 170000 });
    const loud = await page.textContent('#loud');
    assert.match(loud, /LUFS/);
    const fitres = await page.textContent('#fitres');
    assert.match(fitres, /Fit to time: [\d.]+ s of 6 s target \(met\)/, fitres);
    console.log('fit:', fitres);
    console.log('render:', (await page.textContent('#render-status')).trim(), '|', loud.slice(0, 120));

    // play and see captions in sync
    await page.evaluate(() => {
      const a = /** @type {HTMLAudioElement} */ (document.getElementById('player'));
      a.muted = true;
      return a.play();
    });
    await page.waitForFunction(
      () => {
        const t = document.getElementById('caption').textContent;
        return t && !t.startsWith('Press play');
      },
      null,
      { timeout: 15000 },
    );
    const cap = await page.textContent('#caption');
    assert.ok(
      texts.some((t) => cap.includes(t.split(' ')[0])),
      'caption text: ' + cap,
    );

    // ZIP
    const [dl] = await Promise.all([page.waitForEvent('download'), page.click('text=Download ZIP')]);
    const buf = fs.readFileSync(await dl.path()).toString('latin1');
    for (const n of [
      'Browser_test-mix.wav',
      'Browser_test.srt',
      'Browser_test.vtt',
      'Browser_test-timeline.json',
      'Browser_test-stem-Host.wav',
      'Browser_test-stem-Guest.wav',
    ])
      assert.ok(buf.includes(n), 'zip missing ' + n);

    // save, reload, reopen
    await page.keyboard.press('Control+s');
    await page.waitForFunction(() => document.getElementById('proj-status').textContent.startsWith('Saved'));
    await page.evaluate(() => localStorage.clear());
    await page.reload();
    await page.waitForSelector('#projects option[value]:not([value=""])', { state: 'attached' });
    const pid = await page.$eval('#projects option:nth-child(2)', (o) => o.value);
    await page.selectOption('#projects', pid);
    await page.click('#load');
    await page.waitForFunction(() => document.getElementById('proj-status').textContent.startsWith('Opened'));
    assert.equal(await page.inputValue('[aria-label="Line 2"] textarea'), texts[1]);
    assert.equal(await page.inputValue('[aria-label="Line 2 delivery"]'), 'warm');
    assert.equal(await page.inputValue('#title'), 'Browser test');
    assert.ok(await page.isChecked('[aria-label="Use take 2 for line 2"]'), 'chosen take saved');
    await page.screenshot({ path: '/tmp/nv-studio-desktop.png', fullPage: true });

    // mobile
    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForTimeout(300);
    const over = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    assert.ok(over <= 0, `horizontal overflow ${over}px`);
    await page.screenshot({ path: '/tmp/nv-studio-mobile.png', fullPage: true });

    // director's note -> readout -> explicit Apply
    await page.fill('[aria-label="Line 1"] input[id^="note-"]', 'slower, deeper, dramatic pause, flamingo');
    await page.click('[aria-label="Interpret director\'s note for line 1"]');
    await page.waitForFunction(() =>
      document.querySelector('[aria-label="Line 1"]').textContent.includes('What I understood'),
    );
    const readout = await page.textContent('[aria-label="Line 1"]');
    assert.ok(readout.includes('flamingo') && readout.includes('0.92×'), readout.slice(0, 300));
    assert.equal(await page.inputValue('[aria-label="Line 1"] input[id^="speed-"]'), '1'); // not applied yet
    await page.click('[aria-label="Apply director\'s note to line 1"]');
    assert.equal(Number(await page.inputValue('[aria-label="Line 1"] input[id^="speed-"]')), 0.9); // slider step 0.05
    assert.equal(Number(await page.inputValue('[aria-label="Line 1"] input[id^="pitch-"]')), -1);

    // save a custom style from line 2, it appears under My styles
    page.once('dialog', (d) => d.accept('Browser style'));
    await page.click('[aria-label="Save line 2 settings as a style"]');
    await page.waitForFunction(() => document.getElementById('proj-status').textContent.includes('Browser style'));
    assert.ok(await page.$('[aria-label="Line 1 delivery"] optgroup[label="My styles"] option'));

    // rewrite for speech (rules engine, real backend): preview diff, then accept
    await page.fill('[aria-label="Line 3"] textarea', 'Save 50% & more [pause 1s] e.g. today.');
    await page.click('[aria-label="Rewrite line 3 for speech"]');
    await page.click('text=Show rewrite');
    await page.waitForSelector('[aria-label="Line 3"] .diff');
    assert.equal(await page.inputValue('[aria-label="Line 3"] textarea'), 'Save 50% & more [pause 1s] e.g. today.'); // not overwritten
    assert.ok(await page.$('[aria-label="Line 3"] .diff ins'));
    await page.click('text=Accept rewrite');
    const rewritten = await page.inputValue('[aria-label="Line 3"] textarea');
    assert.ok(rewritten.includes('[pause 1s]') && rewritten.includes('percent'), rewritten);
    await page.screenshot({ path: '/tmp/nv-studio-desktop2.png', fullPage: true });
    // remove the test style
    const sts = await (await page.request.get(BASE + '/api/studio/styles')).json();
    for (const x of sts.styles.filter((x) => x.name === 'Browser style'))
      await page.request.delete(`${BASE}/api/studio/styles/${x.id}`);

    // Voice Lab handoff: ?voice=<id> puts that voice on a new line; unknown ids are ignored
    await page.setViewportSize({ width: 1280, height: 900 });
    const before = await page.$$eval('#lines .linecard', (n) => n.length);
    await page.goto(BASE + '/studio.html?voice=bf_emma');
    await page.waitForFunction(() => document.getElementById('proj-status').textContent.includes('Voice Lab'));
    const n = await page.$$eval('#lines .linecard', (x) => x.length);
    assert.equal(n, before + 1);
    assert.equal(await page.inputValue(`[aria-label="Line ${n} voice"]`), 'bf_emma');
    assert.ok(!(await page.url()).includes('voice='));
    await page.waitForTimeout(700); // draft autosave is debounced
    await page.goto(BASE + '/studio.html?voice=custom:ffffffffffff');
    await page.waitForSelector('#lines textarea');
    assert.equal(await page.$$eval('#lines .linecard', (x) => x.length), n);

    // subtitle import switches to timed placement with start/end fields
    await page.click('#paste-box summary');
    page.once('dialog', (d) => d.accept());
    await page.setInputFiles('#subs', {
      name: 'cues.vtt',
      mimeType: 'text/vtt',
      buffer: Buffer.from(
        'WEBVTT\n\n00:00:01.000 --> 00:00:02.500\n<v Ann>Hi there.\n\n00:00:03.000 --> 00:00:04.000\nSecond cue.\n',
      ),
    });
    await page.waitForFunction(() =>
      document.getElementById('paste-status').textContent.startsWith('Imported 2 timed'),
    );
    assert.equal(await page.inputValue('#mode'), 'timed');
    assert.equal(Number(await page.inputValue('[aria-label="Line 1"] input[id^="start-"]')), 1);
    assert.ok(await page.isVisible('[aria-label="Line 2"] input[id^="end-"]'));
    assert.ok(await page.isVisible('#video-box summary'));

    // ---- script writer (no language model: status stubbed so the template engine is used)
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.route('**/api/scriptgen/status', async (r) => {
      const real = await (await r.fetch()).json();
      await r.fulfill({ json: { ...real, llm: { available: false, via: null } } });
    });
    await page.evaluate(() => localStorage.clear());
    await page.goto(BASE + '/studio.html');
    await page.waitForSelector('#lines textarea');
    await page.click('#gen-box summary');
    await page.waitForFunction(() => document.getElementById('gen-engine').textContent.startsWith('No AI connected.'));
    await page.selectOption('#gen-kind', 'dialogue');
    await page.click('#gen-sample');
    await page.waitForSelector('#gen-result:not([hidden])', { timeout: 30000 });
    assert.match(await page.textContent('#gen-badge'), /Built-in outline/);
    const gl = await page.$$eval('#gen-lines .genline', (x) => x.length);
    assert.ok(gl >= 3);
    const castVoices = await page.$$eval('#gen-cast select', (x) => x.map((s) => s.value));
    assert.equal(castVoices.length, 2);
    assert.notEqual(castVoices[0], castVoices[1]);
    page.once('dialog', (d) => d.accept());
    await page.click('#gen-use');
    await page.waitForFunction((n) => document.querySelectorAll('#lines .linecard').length === n, gl);
    assert.equal(await page.inputValue('[aria-label="Line 1 voice"]'), castVoices[0]);
    assert.equal(await page.inputValue('[aria-label="Line 2 voice"]'), castVoices[1]);
    await page.screenshot({ path: '/tmp/nv-gen-desktop.png', fullPage: false });
    // custom brief -> Add to end
    await page.selectOption('#gen-kind', 'ad');
    await page.fill('#gen-topic', "Rosa's bakery");
    await page.fill('#gen-brief', 'fresh bread at 6am\nsourdough every Friday');
    await page.click('#gen-quick button[data-sec="15"]');
    await page.click('#gen-write');
    await page.waitForSelector('#gen-result:not([hidden])');
    assert.match(await page.textContent('#gen-length'), /target 15 s/);
    const add = await page.$$eval('#gen-lines .genline', (x) => x.length);
    await page.click('#gen-append');
    await page.waitForFunction((n) => document.querySelectorAll('#lines .linecard').length === n, gl + add);
    // 503 error path
    await page.route('**/api/scriptgen', (r) =>
      r.fulfill({ status: 503, json: { detail: 'No language model is connected.' } }),
    );
    await page.click('#gen-write');
    await page.waitForFunction(() => document.getElementById('gen-status').classList.contains('error'));
    assert.match(await page.textContent('#gen-status'), /No language model is connected\. Try again/);
    assert.equal(await page.$$eval('#lines .linecard', (x) => x.length), gl + add); // nothing changed
    await page.unroute('**/api/scriptgen');
    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForTimeout(300);
    assert.ok(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
      'gen overflow at 390',
    );
    await page.screenshot({ path: '/tmp/nv-gen-mobile.png', fullPage: false });

    // ---- Connect AI (all LLM endpoints stubbed; no real key is used)
    await page.setViewportSize({ width: 1280, height: 900 });
    const off = {
      available: false,
      via: null,
      provider: null,
      model: 'openai/gpt-4o-mini',
      key_saved: false,
      key_hint: '',
      env_key: false,
      default_model: 'openai/gpt-4o-mini',
    };
    const on = {
      ...off,
      available: true,
      via: 'OpenRouter (openai/gpt-4o-mini)',
      provider: 'OpenRouter',
      key_saved: true,
      key_hint: '…wxyz',
    };
    await page.unroute('**/api/scriptgen/status');
    await page.route('**/api/scriptgen/status', async (r) => {
      const j = await (await r.fetch()).json();
      await r.fulfill({ json: { ...j, llm: off } });
    });
    await page.route('**/api/rewrite/status', async (r) => {
      const j = await (await r.fetch()).json();
      await r.fulfill({ json: { ...j, llm: off } });
    });
    let putCalls = 0;
    await page.route('**/api/llm/key', async (r) => {
      if (r.request().method() === 'PUT') {
        putCalls++;
        if (putCalls === 1)
          return r.fulfill({
            status: 502,
            json: { detail: 'OpenRouter rejected this key. Check it was copied in full.' },
          });
        return r.fulfill({ json: on });
      }
      if (r.request().method() === 'DELETE') return r.fulfill({ json: off });
      return r.continue();
    });
    await page.goto(BASE + '/studio.html');
    await page.waitForSelector('#lines textarea');
    await page.click('#gen-box summary');
    await page.waitForFunction(() => document.getElementById('gen-engine').textContent.startsWith('No AI connected.'));
    assert.ok(await page.isHidden('#ai-connected'));
    await page.click('#ai-box summary');
    assert.equal(await page.getAttribute('#ai-key', 'type'), 'password');
    assert.equal(await page.getAttribute('#ai-box a', 'rel'), 'noopener');
    assert.equal(await page.getAttribute('#ai-model', 'placeholder'), 'openai/gpt-4o-mini');
    await page.screenshot({ path: '/tmp/nv-ai-desktop.png', fullPage: false, clip: undefined });
    const KEY = 'TESTKEY-not-a-real-key-wxyz';
    await page.fill('#ai-key', KEY);
    await page.click('#ai-connect');
    await page.waitForFunction(() => document.getElementById('ai-status').classList.contains('error'));
    assert.match(await page.textContent('#ai-status'), /rejected this key/);
    await page.click('#ai-connect');
    await page.waitForFunction(() => document.getElementById('ai-status').textContent.startsWith('Connected via'));
    assert.equal(await page.inputValue('#ai-key'), '');
    const html = await page.content();
    assert.ok(!html.includes(KEY) && !html.includes('TESTKEY'), 'key leaked into the page');
    assert.ok(!(await page.evaluate(() => JSON.stringify(localStorage))).includes('TESTKEY'), 'key in localStorage');
    assert.match(await page.textContent('#gen-engine'), /Using your language model \(via OpenRouter/);
    assert.match(
      await page.textContent('#ai-connected-text'),
      /Connected: OpenRouter \(key …wxyz, model openai\/gpt-4o-mini\)/,
    );
    assert.ok(await page.isHidden('#ai-box'));
    // rewrite panel now offers the language model
    await page.fill('[aria-label="Line 1"] textarea', 'Hello 50% world.');
    await page.click('[aria-label="Rewrite line 1 for speech"]');
    assert.ok(await page.isEnabled('[aria-label="Line 1"] .rewrite input[type=checkbox] >> nth=1'));
    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForTimeout(300);
    assert.ok(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
      'AI panel overflow at 390',
    );
    page.once('dialog', (d) => d.accept());
    await page.click('#ai-disconnect');
    await page.waitForFunction(() => document.getElementById('gen-engine').textContent.startsWith('No AI connected.'));
    assert.ok(
      consoleText.every((t) => !t.includes('TESTKEY')),
      'key in console',
    );

    // clean up the saved project
    await page.request.delete(`${BASE}/api/studio/projects/${pid}`);
    assert.deepEqual(errors, []);
    console.log('browser_studio: OK');
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  console.error('page errors:', errors);
  process.exit(1);
});
