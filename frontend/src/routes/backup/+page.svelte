<script lang="ts">
  import { request } from '#lib/api.ts';
  import { applyBrowserSettings, MAX_ARCHIVE, readBrowserSettings, type RestoreResult } from '#lib/backup.ts';
  import { PRODUCT } from '#lib/nav.ts';

  let busy = $state(false);
  let status = $state('');
  let restored = $state<RestoreResult | null>(null);
  let files = $state<FileList | null>(null);
  let replace = $state(false);

  async function run(work: () => Promise<void>) {
    busy = true;
    status = 'Working. Keep this page open.';
    try {
      await work();
    } catch (error) {
      status = error instanceof Error ? error.message : 'Something went wrong.';
    } finally {
      busy = false;
    }
  }

  function download() {
    void run(async () => {
      const response = await request('/api/backups/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(readBrowserSettings(localStorage)),
      });
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = url;
      link.download = 'shark-audio-backup.zip';
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
      status = 'Download requested. Confirm it completed, then keep a copy off this computer.';
    });
  }

  function restore(event: SubmitEvent) {
    event.preventDefault();
    void run(async () => {
      const file = files?.[0];
      if (!file || file.size > MAX_ARCHIVE) throw new Error('Choose a ZIP up to 4 GB.');
      restored = (await (
        await request('/api/backups/restore', { method: 'POST', body: file })
      ).json()) as RestoreResult;
      status = 'Restore verified. Current data was not replaced.';
    });
  }

  function recover() {
    void run(async () => {
      const settings = (await (await request('/api/backups/browser')).json()) as Record<string, unknown>;
      applyBrowserSettings(localStorage, settings, replace);
      status = 'Browser settings restored. Reopen Clean and Studio.';
    });
  }
</script>

<svelte:head><title>Backup and restore · {PRODUCT}</title></svelte:head>

<h1>Backup and restore</h1>
<p>
  Available on this computer only. Close other editing tabs and wait for audio jobs to finish. Run only one server per
  data folder.
</p>

<section class="card" aria-labelledby="exportHeading">
  <h2 id="exportHeading">Download a backup</h2>
  <p>
    Includes saved projects, custom voice vectors, cloned voice references, sample collections, delivery styles,
    favorites, and this browser's Clean templates and Studio draft. Maximum 4 GB.
  </p>
  <p>
    Excludes API keys, phone access tokens, downloaded models, caches, temporary render outputs, and uploaded music or
    video. Download finished renders separately; keep original media for re-upload.
  </p>
  <p>
    The ZIP is not encrypted and contains private recordings. Keep it private and copy it to another device or trusted
    backup storage. Changes after this download are not protected.
  </p>
  <button id="backupExport" class="btn" type="button" disabled={busy} onclick={download}>Download backup</button>
</section>

<section class="card" aria-labelledby="restoreHeading">
  <h2 id="restoreHeading">Restore into a new folder</h2>
  <p>
    Checks every file against the archive manifest. Never replaces current projects, voices or references. Only restore
    backups you trust.
  </p>
  <form id="backupRestoreForm" onsubmit={restore}>
    <label for="backupFile">{PRODUCT} backup ZIP</label>
    <input id="backupFile" type="file" accept=".zip,application/zip" required bind:files />
    <button id="backupRestore" class="btn" type="submit" disabled={busy}>Verify and restore</button>
  </form>
  {#if restored}
    <pre id="backupDestination">Restored {restored.files} files to:
{restored.folder}

Your running app is unchanged. Stop it, then run this from the app folder:
{restored.restart}

Return here to recover browser settings. Reconnect API providers separately.</pre>
  {/if}
</section>

<section class="card" aria-labelledby="browserHeading">
  <h2 id="browserHeading">Recover browser settings</h2>
  <p>
    After restarting with the restored folder, return here to recover its templates and draft. Existing browser values
    are kept unless you explicitly allow replacement. Close Studio and Clean tabs first.
  </p>
  <label
    ><input id="backupReplace" type="checkbox" bind:checked={replace} />Replace existing templates and draft in this
    browser</label
  >
  <button id="backupBrowser" class="btn secondary" type="button" disabled={busy} onclick={recover}
    >Recover browser settings</button
  >
</section>

<p id="backupStatus" role="status" aria-live="polite">{status}</p>

<style>
  .card {
    margin-block: 20px;
  }
  label {
    display: block;
    margin-block: 12px;
  }
  input[type='file'] {
    max-width: 100%;
  }
  pre {
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }
</style>
