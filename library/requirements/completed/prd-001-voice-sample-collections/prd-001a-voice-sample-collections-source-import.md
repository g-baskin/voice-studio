# PRD-001a: Source import and analysis *(Retroactive)*

> **Status:** Shipped. Parent: [PRD-001](./prd-001-voice-sample-collections-index.md)

## What was built

- **Inputs.** Exactly one of a local file or a YouTube URL (`src/naturalvoice/sample_library_api.py:144-145`). Allowed extensions: `src/naturalvoice/sample_library.py:34`. Expected speakers 0 (automatic) to 16 (`src/naturalvoice/sample_library_api.py:147-148`).
- **Window.** Start 0 to 28,800 s, length 5 to 120 s (`src/naturalvoice/sample_library.py:134-138`).
- **YouTube restriction.** Only HTTPS youtube.com / youtu.be video IDs, canonicalized to a watch URL (`src/naturalvoice/sample_library.py:110-131`). Download uses yt-dlp with no playlist, 250 MB cap, 30 minute duration filter, no live streams, 300 s timeout (`src/naturalvoice/sample_library.py:179-217`). Live behavior: **unverified**.
- **Decode.** FFmpeg with protocol and format whitelists extracts the window as stereo 44.1 kHz PCM16 (`src/naturalvoice/sample_library.py:141-176`); disguised playlists are rejected (`tests/test_sample_library.py:274`).
- **Job control.** One job at a time via the shared app semaphore; a busy server returns 429 (`src/naturalvoice/sample_library_api.py:159-160`, `98-101`). Analysis runs in a background thread that releases the lock (`src/naturalvoice/sample_library_api.py:104-112`).
- **Media engine.** A separate Python 3.12 environment installed explicitly by `scripts/setup_media_engine.sh:5-6`; readiness check `src/naturalvoice/sample_library.py:103-107`; 503 when absent (`src/naturalvoice/sample_library_api.py:157-158`). The worker reads one JSON request on stdin (`engines/media/worker.py:107-110`), optionally separates vocals with Spleeter in 10 s chunks with 1 s context (`engines/media/worker.py:35-62`), writes `dialogue.wav` (`:69`), and diarizes with pyannote segmentation plus 3D-Speaker embeddings (`:72-88`). Each turn is flagged `overlap` when it intersects a different speaker (`:99-103`).
- **Result validation.** Duration and timeline are checked before publication (`src/naturalvoice/sample_library.py:241-248`). Failures keep the source and expose a generic error without subprocess output (`src/naturalvoice/sample_library.py:249-257`; `tests/test_sample_library.py:259`).
- **Interrupted and retry.** A running record from another process id is shown as interrupted (`src/naturalvoice/sample_library.py:260-264`) and can be retried (`src/naturalvoice/sample_library_api.py:214-233`; `tests/test_sample_library.py:247`).

## Not built

Per-person separation of simultaneous speech (Spleeter targets vocals vs accompaniment only, `engines/media/worker.py:35-62`). Speaker labels are source-local clusters (`engines/media/worker.py:81`), not identity recognition.
