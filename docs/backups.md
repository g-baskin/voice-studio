# Backup and restore

Open **Backup** in the app navigation on this computer. Network devices cannot export or restore data.
Close other editing tabs and wait for audio jobs to finish. Use only one server per data folder.

## Download

Choose **Download backup** and confirm the browser finishes downloading the ZIP. It contains:

- Saved Studio projects and custom delivery styles.
- Custom voice vectors, cloned voice reference recordings and their metadata.
- Sample collections, original imported sources, approved samples and reference-version records.
- Voice favorites, this browser's Clean templates and autosaved Studio draft.

It does **not** contain API keys, phone-access tokens, models, caches, completed temporary renders or
uploaded Studio music/video. Save final renders separately and keep original media for re-upload.
Browser settings come only from this browser and origin; templates on another phone/browser are not included.
A project with temporary media IDs needs its music/video re-uploaded after restore.

The archive is not encrypted. It contains private scripts and recordings. Store it privately and keep a copy
on another device or trusted backup storage. This is a manual snapshot, not automatic backup: changes since
the last download can be lost. A copy on the same disk does not protect against disk failure.

Limits: 4 GB of saved files, 20,000 files, 2 MB of browser settings and manifest metadata. Larger libraries
need a separately managed filesystem backup. Symlinks and unfinished temporary files cause an error rather
than an incomplete success. The app blocks overlapping writes while exporting, refuses export during an
audio job and checks file inventory again afterward. It does not coordinate multiple server processes or
external filesystem editors; avoid either during backup.

## Restore without overwriting

1. Choose your trusted ZIP, then **Verify and restore**.
2. The app checks the format, filenames, limits and every SHA-256 checksum. Checksums detect corruption,
   not a malicious author: they do not authenticate the archive.
3. Success shows a new owner-only folder beside your current data folder. Existing data is never replaced.
4. Stop the app. From its checkout, run the command shown on the Backup page. It sets `NATURALVOICE_DATA`
   to the restored folder and starts the app. Keep using that setting on later launches; the desktop
   launcher does not automatically change its data directory.
5. Return to **Backup**, then **Recover browser settings**. Existing templates/drafts are preserved unless
   you explicitly check the replacement box. Close Clean/Studio tabs first so they do not autosave stale data.
6. Confirm your projects, voices and references. Reconnect AI providers and reopen the new phone access link
   if using network mode. Keep the original data folder until you have verified the restored one.

A failed restore removes only the newly allocated restore folder. It never merges into your active folder.
Successful restores are kept until you choose to remove them. Check free disk space: restore needs space
for the uploaded ZIP plus its expanded contents. The original folder remains your rollback path.

## Restore verification

`tests/test_backup.py::test_restore_drill` exports disposable fixture data, adds a canary afterward,
restores separately, compares every saved byte and checks that the canary is absent from the restore but
still exists in the original. The browser suite downloads a real ZIP, restores it, verifies projects and
checks explicit consent before replacing browser settings. Neither test reads your actual recordings.

These tests prove the fixture path, not a recovery time for your library. Measure your own restore to a
separate folder periodically, especially after accumulating new source recordings.
