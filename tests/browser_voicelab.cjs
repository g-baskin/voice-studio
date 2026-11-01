// Voice Lab end-to-end check. Run against a live server:
// PLAYWRIGHT_MODULE=... NV_URL=http://127.0.0.1:8771 node tests/browser_voicelab.cjs
const chromium = require('./browser_support.cjs');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');

const URL = (process.env.NV_URL || 'http://127.0.0.1:8771') + '/voicelab.html';

function wav(seconds = 12) {
  // tone bursts: valid 10-60 s reference, fast to generate
  const sr = 16000,
    n = sr * seconds,
    b = Buffer.alloc(44 + n * 2);
  b.write('RIFF');
  b.writeUInt32LE(b.length - 8, 4);
  b.write('WAVEfmt ', 8);
  b.writeUInt32LE(16, 16);
  b.writeUInt16LE(1, 20);
  b.writeUInt16LE(1, 22);
  b.writeUInt32LE(sr, 24);
  b.writeUInt32LE(sr * 2, 28);
  b.writeUInt16LE(2, 32);
  b.writeUInt16LE(16, 34);
  b.write('data', 36);
  b.writeUInt32LE(n * 2, 40);
  for (let i = 0; i < n; i++)
    b.writeInt16LE(
      Math.round(6000 * Math.sin((2 * Math.PI * 160 * i) / sr) * Number(Math.sin((2 * Math.PI * 2 * i) / sr) > 0)),
      44 + 2 * i,
    );
  return b;
}

async function noOverflow(page, label) {
  const w = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  assert.ok(w <= 0, label + ': horizontal overflow ' + w + 'px');
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const created = [];
  let page;
  try {
    page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    page.setDefaultTimeout(90000);
    const errors = [];
    page.on('pageerror', (e) => errors.push(e.message));
    await page.goto(URL);

    // Library
    await page.waitForFunction(() => /of \d+ voices/.test(document.querySelector('#libStatus').textContent));
    const all = await page.locator('#libList li').count();
    assert.ok(all >= 50, 'stock voices listed: ' + all);
    await page.selectOption('#libGender', 'male');
    await page.selectOption('#libLang', 'British English');
    const bm = await page.locator('#libList li').count();
    assert.ok(bm > 0 && bm < all);
    for (const t of await page.locator('#libList li .who strong + .hint').allTextContents()) assert.match(t, /^bm_/);
    await page.fill('#libSearch', 'zzzz-none');
    assert.match(await page.textContent('#libStatus'), /No voices match/);
    await page.fill('#libSearch', 'george');
    await page.locator('#libList li button', { hasText: 'Preview' }).first().click();
    await page.waitForFunction(() => {
      const a = /** @type {HTMLAudioElement} */ (document.querySelector('#libAudio'));
      return !a.hidden && a.src.startsWith('blob:');
    });
    await page.waitForFunction(
      () => /** @type {HTMLAudioElement} */ (document.querySelector('#libAudio')).duration > 1,
    );
    await page.selectOption('#libGender', '');
    await page.selectOption('#libLang', '');
    await page.fill('#libSearch', '');
    await page.screenshot({
      path: require('node:path').join(
        process.env.NV_SCREENSHOTS || require('node:os').tmpdir(),
        'nv-voicelab-desktop.png',
      ),
      fullPage: false,
    });

    // Keyboard tab switching
    await page.focus('#tab-library');
    await page.keyboard.press('ArrowRight');
    assert.equal(await page.getAttribute('#tab-design', 'aria-selected'), 'true');
    assert.ok((await page.isVisible('#design')) && !(await page.isVisible('#library')));
    assert.equal(await page.evaluate(() => document.activeElement.id), 'tab-design');

    // Design preview + save
    await page.fill('#designText', 'Testing the design preview.');
    await page.click('#designPreview');
    await page.waitForFunction(() => /Preview ready|error/i.test(document.querySelector('#designStatus').textContent));
    assert.match(await page.textContent('#designStatus'), /Preview ready/);
    await page.fill('#designName', '<b>Browser Mix</b>');
    await page.click('#designSave');
    await page.waitForFunction(() => /Saved/.test(document.querySelector('#designSaveStatus').textContent));
    await page.screenshot({
      path: require('node:path').join(
        process.env.NV_SCREENSHOTS || require('node:os').tmpdir(),
        'nv-voicelab-design.png',
      ),
    });

    // It appears in the Library as text, then rename + delete
    await page.click('#tab-library');
    await page.selectOption('#libKind', 'custom');
    const row = page.locator('#libList li', { hasText: '<b>Browser Mix</b>' });
    await row.waitFor();
    assert.equal(await page.locator('#libList b').count(), 0, 'names must not be parsed as HTML');
    created.push((await row.locator('.who .hint').first().textContent()).trim());
    await row.locator('button', { hasText: 'Edit' }).click();
    assert.equal(await page.getAttribute('#tab-design', 'aria-selected'), 'true');
    assert.equal(await page.locator('#mixRows .mix').count(), 2);
    await page.click('#tab-library');
    await row.locator('button', { hasText: 'Rename' }).click();
    await page.fill('#libList input[aria-label="New name"]', 'Renamed Mix');
    await page.keyboard.press('Enter');
    const renamed = page.locator('#libList li', { hasText: 'Renamed Mix' });
    await renamed.waitFor();
    page.once('dialog', (d) => d.accept());
    await renamed.locator('button', { hasText: 'Delete' }).click();
    await renamed.waitFor({ state: 'detached' });
    created.pop();

    // Describe -> 3 options, play one, save one
    await page.click('#tab-describe');
    await page.fill('#descPrompt', 'warm, deep male narrator, British');
    await page.click('#descGo');
    await page.waitForFunction(() => document.querySelectorAll('#descOptions .option').length === 3);
    assert.match(await page.textContent('#descStatus'), /male.*British English.*lower pitch/);
    const opt = page.locator('#descOptions .option').first();
    await opt.locator('button', { hasText: 'Play option 1' }).click();
    await page.waitForFunction(() =>
      /** @type {HTMLAudioElement} */ (document.querySelector('#descOptions .option audio')).src.startsWith('blob:'),
    );
    await opt.locator('input').fill('Described Voice');
    await opt.locator('button', { hasText: 'Save' }).click();
    await page.waitForFunction(() => /Saved/.test(document.querySelector('#descOptions .option .status').textContent));
    const lib = await (
      await page.request.get(
        process.env.NV_URL
          ? process.env.NV_URL + '/api/voicelab/library?kind=custom'
          : 'http://127.0.0.1:8771/api/voicelab/library?kind=custom',
      )
    ).json();
    const desc = lib.voices.find((v) => v.name === 'Described Voice');
    assert.ok(desc && desc.meta.source === 'describe');
    created.push(desc.id);

    // Match: consent required, then start, see progress, cancel cleanly
    await page.click('#tab-match');
    const ref = path.join(os.tmpdir(), 'nv-voicelab-ref.wav');
    fs.writeFileSync(ref, wav());
    await page.setInputFiles('#matchFile', ref);
    await page.selectOption('#matchBudget', '60');
    await page.click('#matchGo');
    assert.match(await page.textContent('#matchStatus'), /permission/);
    await page.check('#matchConsent');
    await page.click('#matchGo');
    await page.waitForFunction(
      () => /Comparing|Measuring|Refining/.test(document.querySelector('#matchStatus').textContent),
      null,
      { timeout: 60000 },
    );
    assert.ok(await page.isVisible('#matchCancel'));
    await page.click('#matchCancel');
    await page.waitForFunction(() => /Cancelled|Done/.test(document.querySelector('#matchStatus').textContent), null, {
      timeout: 120000,
    });
    assert.ok(await page.isEnabled('#matchGo'));

    // Clone tab shows the panel filled by clone.js (reached via the Match link)
    await page.click('#goClone');
    assert.equal(await page.getAttribute('#tab-clone', 'aria-selected'), 'true');
    assert.ok(await page.isVisible('#clonePanel'));
    assert.ok((await page.locator('#clonePanel').evaluate((n) => n.children.length)) > 0, 'clone.js filled the panel');

    // Mobile
    await page.setViewportSize({ width: 390, height: 844 });
    for (const t of ['library', 'design', 'describe', 'match', 'clone']) {
      await page.click('#tab-' + t);
      await noOverflow(page, t);
    }
    await page.click('#tab-library');
    await page.selectOption('#libKind', '');
    await page.screenshot({
      path: require('node:path').join(
        process.env.NV_SCREENSHOTS || require('node:os').tmpdir(),
        'nv-voicelab-mobile.png',
      ),
    });
    await page.click('#tab-design');
    await page.screenshot({
      path: require('node:path').join(
        process.env.NV_SCREENSHOTS || require('node:os').tmpdir(),
        'nv-voicelab-mobile-design.png',
      ),
      fullPage: true,
    });

    assert.deepEqual(errors, []);
    console.log('voicelab browser check passed');
  } finally {
    for (const id of created) {
      try {
        await page.request.delete(
          (process.env.NV_URL || 'http://127.0.0.1:8771') + '/api/voicelab/voices/' + encodeURIComponent(id),
        );
      } catch {
        /* best effort */
      }
    }
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
