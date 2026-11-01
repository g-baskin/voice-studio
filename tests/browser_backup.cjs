const { launch } = require('./browser_support.cjs');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const base = process.env.NV_URL;
if (!base || !process.env.NATURALVOICE_DATA) throw new Error('Run through npm run test:browser.');
(async () => {
  const browser = await launch({ headless: true });
  try {
    const page = await browser.newPage({ acceptDownloads: true });
    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto(base + '/backup');
    const draft = JSON.stringify({ project: { title: 'Backed-up draft' }, projectId: null });
    const templates = JSON.stringify({
      archive: {
        name: 'Saved template',
        preset: 'light',
        settings: { ai_clean: 0, dereverb: 0, demetal: 0.25, deharsh: 0.2, warmth: 0.25, denoise: 0, room_tone: 0 },
      },
    });
    const expected = { 'nv-studio-draft-v1': draft, 'naturalvoice.templates.v1': templates };
    await page.evaluate((values) => {
      for (const [key, value] of Object.entries(values)) localStorage.setItem(key, value);
    }, expected);
    const project = await page.request.post(base + '/api/studio/projects', {
      data: { title: 'Backup fixture', lines: [] },
    });
    assert.equal(project.status(), 200);
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.getByRole('button', { name: 'Download backup', exact: true }).click(),
    ]);
    const archive = await download.path();
    assert.equal(download.suggestedFilename(), 'shark-audio-backup.zip');
    const before = fs.readdirSync(path.join(process.env.NATURALVOICE_DATA, 'projects'));
    await page.setInputFiles('#backupFile', archive);
    const [response] = await Promise.all([
      page.waitForResponse((r) => r.url().endsWith('/api/backups/restore')),
      page.getByRole('button', { name: 'Verify and restore' }).click(),
    ]);
    assert.equal(response.status(), 201);
    await page.waitForFunction(() => document.getElementById('backupStatus').textContent.includes('Restore verified'));
    const parent = path.dirname(process.env.NATURALVOICE_DATA);
    const restored = fs.readdirSync(parent).filter((name) => name.startsWith('voice-studio-restored-'));
    assert.equal(restored.length, 1);
    const folder = path.join(parent, restored[0]);
    const result = { folder, browser: JSON.parse(fs.readFileSync(path.join(folder, 'browser-settings.json'), 'utf8')) };
    await page.waitForFunction(() => document.getElementById('backupStatus').textContent.includes('Restore verified'));
    assert.notEqual(result.folder, process.env.NATURALVOICE_DATA);
    assert.deepEqual(fs.readdirSync(path.join(process.env.NATURALVOICE_DATA, 'projects')), before);
    assert.deepEqual(fs.readdirSync(path.join(result.folder, 'projects')), before);
    assert.equal(result.browser['nv-studio-draft-v1'], draft);
    assert.equal(result.browser['naturalvoice.templates.v1'], templates);
    fs.writeFileSync(process.env.NV_RESTORE_RECEIPT, JSON.stringify(result), { flag: 'wx' });
    // The runner restarts against this folder; this page checks replacement consent independently.
    const existing = { 'nv-studio-draft-v1': '{"project":{"title":"Keep this"}}', 'naturalvoice.templates.v1': '{}' };
    await page.evaluate((values) => {
      for (const [key, value] of Object.entries(values)) localStorage.setItem(key, value);
    }, existing);
    await page.route('**/api/backups/browser', (route) => route.fulfill({ json: result.browser }));
    await page.getByRole('button', { name: 'Recover browser settings' }).click();
    await page.waitForFunction(() =>
      document.getElementById('backupStatus').textContent.includes('Existing browser data kept'),
    );
    assert.deepEqual(
      await page.evaluate(() => ({
        'nv-studio-draft-v1': localStorage.getItem('nv-studio-draft-v1'),
        'naturalvoice.templates.v1': localStorage.getItem('naturalvoice.templates.v1'),
      })),
      existing,
    );
    await page.check('#backupReplace');
    await page.getByRole('button', { name: 'Recover browser settings' }).click();
    await page.waitForFunction(() =>
      document.getElementById('backupStatus').textContent.includes('Browser settings restored'),
    );
    assert.deepEqual(
      await page.evaluate(() => ({
        'nv-studio-draft-v1': localStorage.getItem('nv-studio-draft-v1'),
        'naturalvoice.templates.v1': localStorage.getItem('naturalvoice.templates.v1'),
      })),
      expected,
    );
    await page.setInputFiles('#backupFile', {
      name: 'bad.zip',
      mimeType: 'application/zip',
      buffer: Buffer.from('invalid'),
    });
    await page.getByRole('button', { name: 'Verify and restore' }).click();
    await page.waitForFunction(() => document.getElementById('backupStatus').textContent.includes('Restore failed'));
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    assert.deepEqual(errors, []);
    console.log(
      'Backup browser passed: download, separate restore, data preservation, browser consent, invalid ZIP, mobile reflow.',
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
