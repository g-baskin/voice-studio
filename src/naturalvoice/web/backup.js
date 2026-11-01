'use strict';
const backupKeys = ['nv-studio-draft-v1', 'naturalvoice.templates.v1'];
const backupStatus = document.getElementById('backupStatus');
const exportButton = document.getElementById('backupExport');
const restoreButton = document.getElementById('backupRestore');
const browserButton = document.getElementById('backupBrowser');
async function backupRequest(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Backup request failed.');
  }
  return response;
}
async function backupAction(work) {
  for (const button of [exportButton, restoreButton, browserButton]) button.setAttribute('disabled', '');
  backupStatus.textContent = 'Working. Keep this page open.';
  try {
    await work();
  } catch (error) {
    backupStatus.textContent = error.message;
  } finally {
    for (const button of [exportButton, restoreButton, browserButton]) button.removeAttribute('disabled');
  }
}
exportButton.addEventListener('click', () => {
  void backupAction(async () => {
    const settings = {};
    for (const key of backupKeys) {
      const value = localStorage.getItem(key);
      if (value !== null) settings[key] = value;
    }
    const response = await backupRequest('/api/backups/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings),
    });
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement('a');
    link.href = url;
    link.download = 'voice-studio-backup.zip';
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
    backupStatus.textContent = 'Download requested. Confirm it completed, then keep a copy off this computer.';
  });
});
document.getElementById('backupRestoreForm').addEventListener('submit', (event) => {
  event.preventDefault();
  void backupAction(async () => {
    const input = document.getElementsByTagName('input')[0];
    const file = input.files[0];
    if (!file || file.size > 4 * 1024 ** 3 + 32 * 1024 ** 2) throw new Error('Choose a ZIP up to 4 GB.');
    const result = await (await backupRequest('/api/backups/restore', { method: 'POST', body: file })).json();
    const destination = document.getElementById('backupDestination');
    destination.hidden = false;
    destination.textContent = `Restored ${result.files} files to:\n${result.folder}\n\nYour running app is unchanged. Stop it, then run this from the app folder:\n${result.restart}\n\nReturn here to recover browser settings. Reconnect API providers separately.`;
    backupStatus.textContent = 'Restore verified. Current data was not replaced.';
  });
});
browserButton.addEventListener('click', () => {
  void backupAction(async () => {
    const settings = await (await backupRequest('/api/backups/browser', {})).json();
    const replace = document.getElementsByTagName('input')[1].checked;
    const keys = backupKeys.filter((key) => typeof settings[key] === 'string');
    if (!keys.length)
      throw new Error('No browser settings in this data folder. Restart with the restored folder first.');
    if (!replace && keys.some((key) => localStorage.getItem(key) !== null)) {
      throw new Error('Existing browser data kept. Check the replacement box only if you want to replace it.');
    }
    const before = keys.map((key) => localStorage.getItem(key));
    try {
      for (const key of keys) localStorage.setItem(key, settings[key]);
    } catch (error) {
      for (const [i, key] of keys.entries()) {
        if (before[i] === null) localStorage.removeItem(key);
        else localStorage.setItem(key, before[i]);
      }
      throw error;
    }
    backupStatus.textContent = 'Browser settings restored. Reopen Clean and Studio.';
  });
});
