# Security review: Editor Shorts captions (feature/shorts-captions)

**Mode:** scoped SOURCE REVIEW by the implementing agent, plus an independent read-only auditor pass, plus RUNTIME tests.
**Scope:** the diff from `origin/feature/svelte-pages` to `feature/shorts-captions`:
- **Server:** `transcript.py`, `captions.py`, `editor.py` (the `Captions` model and the caption overlay input), and `editor_api.py` (transcript jobs, transcript edits, hooks, caption fonts, SRT).
- **Speech engine:** `engines/media/transcribe.py`.
- **Model download:** `scripts/download_speech_model.py` and `scripts/setup_speech_model.sh`.
- **Client:** `frontend/src/lib/editor/` and the three new panels.

**Coverage:** reduced. The security-stinger catalog is built for SvelteKit, Neon, WorkOS and Stripe. This app is a loopback FastAPI server with a static SvelteKit build. The generic surfaces were applied instead: injection, paths, untrusted subprocess output, resource bounds, file serving, LLM data flow, client rendering, supply chain.

## Executive summary

- Findings: 0 Critical, 0 High, 0 Medium, 3 Low (all fixed).
- Ship Gate status: cleared to proceed to the Quality review.

## Findings

### Low (fixed): hook search had no work limit

- **Location:** `src/naturalvoice/transcript.py:401-406` (the `for sj in range(si, len(spans))` window loop).
- **Description:** the loop stops only when a window passes the longest length. `validate_words` allows zero-length words, so the owner could save a transcript of 200,000 words that all sit at 0 s (`PUT .../transcript`). No window would ever reach the longest length, so the loop would make about 2×10^10 passes and tie up a server thread. Each window also summed its gaps and pauses one by one.
- **Remediation:**
  - The search now stops with a plain error after `MAX_HOOK_STEPS` (2,000,000) windows.
  - Gaps and pause cover now use prefix sums, so each window costs the same no matter how long it is. Overlapping pauses are merged first.
  - Measured: a 5-hour transcript takes 1.8 s with a 15 to 90 s range, and 12.6 s with 5 to 600 s.
  - RUNTIME: `test_hook_search_has_a_work_budget_and_counts_pauses_by_overlap`.

### Low (fixed): a stalled speech worker held the processing slot

- **Location:** `src/naturalvoice/transcript.py:170-182` (`watch`).
- **Description:** a worker that hung without printing would hold the shared `processing` slot until the owner pressed Cancel. Exports and imports were blocked meanwhile.
- **Remediation:** the watcher kills the worker after `worker_deadline(duration)`, which is 3 × the media length + 300 s, and the job fails with "took too long". RUNTIME: `test_a_stalled_worker_is_stopped_at_its_deadline` checks that the wav is removed and nothing is saved.

### Low (fixed): an SRT request for media no longer in the bin returned 500

- **Location:** `src/naturalvoice/editor_api.py:466-472` (`sequence_srt`). The same guard was added to `hooks_find`.
- **Description:** `read_transcript` raises `EditorError` for an unknown media id. The error was not caught, so the response was a generic 500 rather than a clear 400.
- **Remediation:** the error is now caught and turned into a 400 with the plain message. RUNTIME: the new assertion in the `tests/test_editor.py` transcript API test.

## Surface coverage

### Command and filter-graph injection

None detected.
- **Argument lists.** Every new ffmpeg and worker call passes an argument list, never a shell:
  - `transcript.py:_decode` uses `INPUT_GUARD`, `-map 0:a:0` and fixed codec arguments.
  - The caption input in `editor.py:718` is `-framerate`, the rate from `FPS_RATES`, `-start_number 0`, `INPUT_GUARD`, `-f image2` and a fixed `%07d.png` pattern inside the export's own temporary folder.
- **Filter graph.** The caption overlay adds only an integer `y` (from `captions.band`) and fixed labels to the filter graph.
- **No user strings.** Caption colours are checked against `^#[0-9a-fA-F]{6}$` and go only to Pillow. No transcript text reaches ffmpeg; Pillow draws it as pixels.

### Path traversal and file names

None detected.
- **Media folders.** Media ids pass `identifier` before `media_dir` builds any path. `transcript.json`, `levels.json` and `speech-16k.wav` are fixed names inside that folder.
- **Caption track.** The caption track id must match `_SHORT_ID` and must exist in the sequence (`Sequence._consistent`).
- **Export temporary folder.** Caption strips live in `<export>.captions` next to the export file, under the job's own folder, and `render` always removes them in `finally` (`editor.py:792`).
- **SRT file name.** The SRT name goes through `_filename` (`_SAFE_NAME`).

### Untrusted worker output

None detected.
- **Size and shape.** Worker stdout is limited to 16 MiB, and each line must be complete JSON and a dict (`transcript.py:190-199`).
- **Content.** Words go through `validate_words`. That allows at most 200,000 words, requires finite times inside the media in non-decreasing order, and requires 1 to 48 characters of NFC text with no control, surrogate, private-use, unassigned or bidi-override characters.
- **Error text.** Worker stderr goes to DEVNULL and is never shown.
- **Cleanup.** The worker is killed in `finally`, and the temporary wav is removed in `finally` on every path. RUNTIME: tests for bad output, cancel and deadline.

### Resource bounds

None detected beyond the fixed Lows.
- **Shared slot.** Transcription shares the single `processing` slot and gets 429 when it is busy.
- **Overlap guards.** Running a second job on the same file, saving edits, or removing the file during a run gets 409.
- **Job pruning.** Finished job records are pruned like analysis jobs.
- **Request limits.**
  - Transcript edits are capped at 200,000 items.
  - Hooks allow `count` up to 20 and lengths from 5 to 600 s.
- **Caption export limits.**
  - Captioned exports are capped at 30 minutes, checked before the job starts (`check_export`) and again while drawing.
  - At most 5,000 caption states are drawn.
  - Each output frame is a hardlink, with a copy as the fallback.

### Caption font endpoint

None detected. `caption_font` accepts only keys in `captions.FONTS` and serves only the fixed absolute system paths listed there. No part of the request becomes a path. Unknown keys and missing files return 404.

### LLM ranking

None detected.
- **Opt-in.** Ranking runs only when the request sets `use_ai` and a provider is configured.
- **Data sent.** It sends only candidate ids and the first 160 characters of each candidate's text, for at most 20 candidates. The system prompt tells the model to treat that text as data.
- **Reply parsing.** Only integer ids that already exist are accepted, so a hostile transcript can at most change the order.
- **Errors.** Provider errors use the existing `llm._explain` plain-language messages. They name the provider and model, never the key.

### SRT and text output

None detected. The SRT is `text/plain; charset=utf-8`, sent as an attachment with `X-Content-Type-Options: nosniff` and a sanitised file name. Words cannot contain newlines, so they cannot add SRT blocks.

### Client rendering (XSS)

None detected. There is no `{@html}`, `innerHTML` or `eval` in the new sources. Transcript words, hook text and reasons are rendered as Svelte text. Captions are drawn with canvas `fillText`. `FontFace` URLs are built from the typed font key.

### Model download and supply chain

None detected.
- **Download.** The downloader uses a pinned HTTPS commit URL (`download_speech_model.py:12`, asserted at `:55`). It checks the exact size and SHA-256 of every file, writes to `.part` files with an atomic rename, and checks disk space first. Redirects stay within urllib's HTTPS handling, and the hash check makes the final host irrelevant.
- **Dependencies.** `pillow>=13.0.0` was made a direct dependency. It was already locked at 13.0.0 as a transitive dependency, and the `uv.lock` diff only adds the direct edge. The engine's `uv.lock` is unchanged. `package-lock.json` is unchanged.
- **Licence.** The model is CC-BY-4.0. Attribution is written to `ATTRIBUTION.txt` and shown in the setup state.

### Secrets, webhooks, headers, PII and logging

Not applicable or unchanged.
- No new secrets or environment variables.
- No webhooks, and no new logging or telemetry.
- Transcripts stay in the owner's data folder.

## Re-evaluation

After the fixes, the full pass was repeated over the changed functions (`hook_candidates`, `_run_worker`, `transcribe`, `sequence_srt`, `hooks_find`). The following were rerun:
- ruff
- `tests/test_transcript.py`: 18 passed
- the transcript, caption and hook API tests in `tests/test_editor.py`
- the full suite and `npm run check`, as recorded in the workflow log

## Not checked

- sherpa-onnx's and ffmpeg's own handling of malformed audio.
- Font parsing inside FreeType (only fixed system fonts are loaded).
- LocalAccess internals.
- Fuzzing.

No whole-application security claim is made.
