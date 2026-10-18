const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');

function wav(seconds = 4) {
  const sr = 24000, n = sr * seconds, b = Buffer.alloc(44 + n * 2);
  b.write('RIFF'); b.writeUInt32LE(b.length - 8, 4); b.write('WAVEfmt ', 8);
  b.writeUInt32LE(16, 16); b.writeUInt16LE(1, 20); b.writeUInt16LE(1, 22); b.writeUInt32LE(sr, 24);
  b.writeUInt32LE(sr * 2, 28); b.writeUInt16LE(2, 32); b.writeUInt16LE(16, 34);
  b.write('data', 36); b.writeUInt32LE(n * 2, 40);
  for (let i = 0; i < n; i++) b.writeInt16LE(Math.round(5000 * Math.sin(2*Math.PI*220*i/sr) * (Math.sin(2*Math.PI*i/sr) > -0.5)), 44 + 2*i);
  return b;
}
async function idle(page) { await page.waitForFunction(() => !document.querySelector('#cleanBtn').disabled, {timeout: 90000}); }
(async () => {
  const browser = await chromium.launch({headless: true});
  try {
    const page = await browser.newPage({viewport: {width: 1280, height: 900}});
    page.setDefaultTimeout(90000);
    const errors = []; page.on('pageerror', e => errors.push(e.message));
    await page.goto('http://127.0.0.1:8765');
    await page.waitForSelector('#template:not([disabled])');
    await page.selectOption('#template', 'clean');
    await page.locator('summary', {hasText: 'My saved templates'}).click();
    await page.fill('#templateName', '<b>My voice</b>');
    await page.focus('#s-room_tone'); await page.keyboard.press('ArrowRight');
    await page.click('#saveTemplate');
    const savedId = await page.inputValue('#template');
    assert.ok(savedId.startsWith('saved-'));
    assert.match(await page.textContent('#savedStatus'), /Saved/);
    await page.reload(); await page.waitForSelector('#template:not([disabled])');
    await page.selectOption('#template', savedId);
    assert.equal(Number(await page.inputValue('#s-room_tone')), 0.05);
    assert.equal(await page.locator(`#template option[value="${savedId}"]`).textContent(), 'Saved: <b>My voice</b>');
    await page.locator('summary', {hasText: 'My saved templates'}).click();
    await page.click('#deleteTemplate');
    assert.equal(await page.locator(`#template option[value="${savedId}"]`).count(), 0);
    await page.setInputFiles('#file', {name: 'voice.wav', mimeType: 'audio/wav', buffer: wav()});
    await page.click('#suggestBtn'); await idle(page);
    assert.match(await page.textContent('#suggestion'), /Low confidence/);
    await page.click('#applySuggestion');
    assert.ok(['clean','ad','metallic','echo','noise'].includes(await page.inputValue('#template')));
    await page.selectOption('#template', 'clean');
    await page.fill('#previewStart', '1');
    await page.click('#previewBtn'); await idle(page);
    assert.match(await page.textContent('#resultTitle'), /preview/);
    assert.match(await page.textContent('#resultSettings'), /3s starting at 1s/);
    assert.match(await page.textContent('#metrics'), /Pause level \(not an echo measurement\)/);
    assert.match(await page.textContent('#metrics'), /Exported result/);
    assert.doesNotMatch(await page.textContent('#metrics'), /Lower is better for/);
    await page.waitForFunction(() => [...document.querySelectorAll('#beforeMedia audio, #afterMedia audio')].every(a => a.readyState >= 1));
    await page.evaluate(() => { const slider = document.querySelector('#abSeek'); slider.value = '1'; slider.dispatchEvent(new Event('input', {bubbles:true})); });
    await page.click('#abAfter');
    assert.equal(await page.getAttribute('#abAfter', 'aria-pressed'), 'true');
    assert.ok(Math.abs(await page.locator('#afterMedia audio').evaluate(a => a.currentTime) - 1) < 0.1);
    await page.click('#abPlay');
    await page.waitForFunction(() => !document.querySelector('#afterMedia audio').paused);
    await page.click('#abBefore');
    await page.waitForFunction(() => !document.querySelector('#beforeMedia audio').paused);
    assert.equal(await page.locator('#afterMedia audio').evaluate(a => a.paused), true);
    await page.click('#abPlay');
    await page.setInputFiles('#file', [
      {name: 'bad.wav', mimeType: 'audio/wav', buffer: Buffer.from('invalid audio')},
      {name: 'second.wav', mimeType: 'audio/wav', buffer: wav(2)},
    ]);
    await page.click('#batchBtn'); await idle(page);
    assert.match(await page.textContent('#queueStatus'), /2 completed, 1 failed/);
    assert.equal(await page.locator('#queueList a').count(), 2);
    const downloadPromise = page.waitForEvent('download');
    await page.click('#batchDownload'); const download = await downloadPromise;
    assert.equal(download.suggestedFilename(), 'natural-voice-batch.zip');
    const zip = fs.readFileSync(await download.path()); assert.equal(zip.subarray(0, 2).toString(), 'PK');
    await page.setViewportSize({width: 390, height: 844});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    await page.screenshot({path: '/tmp/naturalvoice-workflow-mobile.png', fullPage: true});
    await page.setViewportSize({width: 1280, height: 900});
    await page.screenshot({path: '/tmp/naturalvoice-workflow-desktop.png', fullPage: true});
    assert.deepEqual(errors, []);
    // Stop control: while first upload is held, request stop; no second file should be sent.
    await page.click('#clearQueue');
    await page.setInputFiles('#file', [
      {name: 'one.wav', mimeType: 'audio/wav', buffer: wav(1)},
      {name: 'two.wav', mimeType: 'audio/wav', buffer: wav(1)},
    ]);
    let release, uploads = 0;
    await page.route('**/api/clean', async route => {
      uploads++; await new Promise(resolve => { release = resolve; });
      await route.fulfill({status: 400, contentType: 'application/json', body: '{"detail":"Test failure"}'});
    });
    await page.click('#batchBtn');
    await page.waitForSelector('#stopQueue:not([hidden])');
    await page.click('#stopQueue');
    assert.ok(release); release(); await idle(page);
    assert.equal(uploads, 1);
    assert.match(await page.textContent('#queueStatus'), /Stopped/);
    assert.match(await page.textContent('#queueList'), /two.wav: queued/);
    console.log('Live browser passed: saved template persistence/delete/plain text, advisory suggestion/apply, real preview/export, synchronized A/B play and seek, mixed-success batch, ZIP download, stop queue, mobile width.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
