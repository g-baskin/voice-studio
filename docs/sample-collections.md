# Voice sample collections

Open **Voice Lab > Voice sample collections** (`/samples`); the Voice Lab Clone tab also links here. This is local reference-based
cloning, not model training. New recordings can improve references, but more audio does not guarantee
better output. The owner explicitly deferred actual model training on this Intel Mac.

## Setup

Run `scripts/setup_media_engine.sh` explicitly. It installs a separate Python 3.12 environment at
`engines/media/.venv`, uses its own checked-in lockfile, and verifies model archive SHA-256 hashes.
The main and Chatterbox environments are not changed. FFmpeg is required. Cloned speech previews
also require the existing Chatterbox installation (`scripts/setup_clone_engine.sh`).

CPU packages: sherpa-onnx 1.13.8, sherpa-onnx-core 1.13.8, numpy 2.2.6, yt-dlp 2026.8.19.
Models are from the k2-fsa/sherpa-onnx GitHub release assets:

- `speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2` (MIT, CNRS license included).
- `speaker-recongition-models/3dspeaker_speech_eres2net_sv_en_voxceleb_16k.onnx`
  (3D-Speaker project, Apache-2.0; English VoxCeleb embedding model).
- `source-separation-models/sherpa-onnx-spleeter-2stems.tar.bz2`
  (Spleeter, MIT, Deezer). Model separation targets vocals/accompaniment, not individual people.

Hashes in `scripts/download_media_models.py` were measured from the downloaded upstream assets on
2026-10-18 (trust on first retrieval), not signed upstream attestations. The installer only extracts
explicit regular-file members; it does not execute scripts from archives. Do not redistribute model
bundles without preserving their license notices and reviewing upstream terms.

## Workflow

1. Choose a local MP3, MP4, WAV, FLAC, M4A, MOV, MKV, WebM, OGG or Opus file, or one public YouTube video.
   Confirm permission to process and clone. Uploads are limited to 250 MB. YouTube audio is limited to
   30 minute videos, 250 MB and a five-minute download timeout; no cookies, account login, playlists,
   generic URL fetches or access bypass. Download availability is not guaranteed.
2. Choose a source start and a 5 to 120 second analysis window. Optional background separation is
   slower and may add artifacts. Supply the expected speaker count or let the model estimate it.
3. Create or select a permitted person. Speaker numbers are source-local, not identity recognition.
4. Listen to original/dialogue audio. Pick a suggested turn or set exact selection start/end values.
   The selected range is relative to the imported window. Confirm it contains only that person's
   voice, then save it. Each sample must be 0.5 to 60 seconds. Choose original audio if separation damages the speech.
5. Import more sources and assign their reviewed selections to the same collection.
6. Select samples totaling 5 to 20 seconds, then build a new reference. It is immediately available
   as a separate cloned voice in Voice Lab and Studio. Old versions remain untouched.
7. Preview versions using the same sentence, then choose a preferred version. Preference is metadata
   for the collection only: it does not silently replace voices in saved Studio projects. Choose the
   version's name in Studio. Re-select an earlier preferred version to roll back the preference.

Known overlapping turns cannot be saved. Diarization can miss overlaps, split one person into several
labels, or merge people. Listen rather than trusting labels. Empty or silent selections are rejected (quiet speech is not);
RMS level and possible clipping flags are measurements, not an overall quality or identity score.
Samples cannot be edited in place: save a corrected range/person assignment and leave the unwanted
sample unchecked when building references. This version has no automatic identity matching, per-person
speech separation, training, transcription, or destructive library management.

## Data and recovery

New data lives under `NATURALVOICE_DATA/sample-library/{sources,people,samples}`. Clone references
remain in the existing `voices` directory, with source/sample IDs in their metadata. Both directories
must be backed up together. Originals are retained; adding samples does not overwrite old audio.
A source interrupted by a server restart is shown as interrupted and can be retried. Failed upload
staging is removed, but accepted source recordings are retained even when analysis fails.

One processing job shares the existing app semaphore. Collection writes use a filesystem lock and
atomic JSON replacement. Run only one server against a given data directory. There is a 2 GB sample
library budget and a 1 GB free-space reserve. Cloned references occupy additional space in `voices`.
No automatic deletion, backup, cloud synchronization or off-device recovery is implemented. A crash
can leave unreferenced new files; do not delete recordings to repair metadata without a backup.

New endpoints require a loopback host and same-origin browser requests. This local feature is not a
multi-user authenticated API. As elsewhere in the app, access to the machine implies access to audio.

## Verification

Fast API/persistence tests: `PYTHONPATH=src uv run --no-sync pytest tests/test_sample_library.py`.
Real-model smoke check: `PYTHONPATH=src uv run --no-sync pytest tests/test_media_engine.py`.
The latter uses generated Kokoro speech and actual separation/diarization, not a user's recording.
Browser checks use `tests/browser_samples.cjs`, `NV_URL` and `PLAYWRIGHT_MODULE`, with a server started
against disposable `NATURALVOICE_DATA`. They write synthetic samples and collection metadata.
