# Security review: Editor Clip mode (feature/clip-mode)

**Mode:** scoped SOURCE REVIEW by the implementing agent (no separate auditor was run), plus RUNTIME tests.
**Scope:** the diff from `origin/feature/editor` to `feature/clip-mode`. On the server that is `editor.py` (subclips, marker colours, silence, scene and moment analysis, analysis cache) and `editor_api.py` (analysis jobs, batch export, per-file download). On the client it is `frontend/src/lib/editor/` and `frontend/src/routes/editor/`.
**Coverage:** reduced. The security-stinger catalog covers SvelteKit, Neon, WorkOS and Stripe; this app is a loopback FastAPI server with a static SvelteKit build. Its generic surfaces (injection, path handling, authorization, resource bounds, client rendering, dependencies) were applied instead.

## Executive summary

- Findings: 0 Critical, 0 High, 0 Medium, 2 Low.
- Ship Gate status: cleared to proceed to the Quality review.

## Findings

### Low (fixed): removing media while it is being analysed left an orphan folder

- **Location:** `src/naturalvoice/editor_api.py:182` (`media_delete`) with `src/naturalvoice/editor.py:1228` (`atomic_json(cached, result)`).
- **Description:** an analysis thread writes its result with `atomic_json`, which runs `mkdir(parents=True)`. If the file was removed mid-run, this recreated `media/<id>/` holding only the analysis JSON. `list_media` skips folders without `media.json`, so the bin did not break, but disk space leaked.
- **Remediation:** `media_delete` now refuses (409) while an analysis of that media is running. RUNTIME: `test_api_analysis_jobs_run_cache_cancel_and_bound_settings` checks that the delete is refused while a job is running and succeeds afterwards.

### Low (accepted): ffmpeg failure text reaches the client

- **Location:** `src/naturalvoice/editor.py:1021` (`raise EditorError(f"Analysis failed: {detail[:300]}")`).
- **Description:** the last ffmpeg stderr line (up to 300 characters) is shown to the user and can include the proxy's local path. This is the same pattern as export (`editor.py:769`). It is a single-user local app behind LocalAccess, and the path belongs to the user's own data folder.

## Surface coverage

### Command and filter-graph injection

None detected. Analysis runs ffmpeg as an argument list, never a shell (`editor.py:985`). Every filter graph is built from numbers that Pydantic bounds (`AnalysisRequest`, `editor_api.py:194`), that are clamped again in `detect_silence`/`detect_scenes`, and that are printed through `_n` (digits, `-` and `.` only). No user string enters a filter graph.

### Untrusted media input

None detected. Analysis reads only the generated proxy, opened with `INPUT_GUARD` (`-protocol_whitelist file` plus the demuxer allowlist). RUNTIME: `test_analysis_will_not_follow_a_playlist_to_other_files`.

### Path traversal and file names

None detected:
- Media ids pass through `identifier` (32 hex characters) before any path is built (`media_dir`).
- Analysis cache names come from the fixed `kind` literal plus formatted numbers (`analysis_key`).
- Batch export names combine the sanitised sequence stem (`_filename`, capped at 40 characters), a two-digit index, and the label reduced by `_SAFE_NAME` to `[A-Za-z0-9 _.-]` (`editor_api.py:378`). Paths are joined under `EXPORTS/<uuid>/`.
- RUNTIME: `test_api_batch_exports_each_range_as_its_own_file` sends the label `Hook <1>/../x` and the file stays in the job folder.

### Authorization and access

None detected. The new routes sit under `/api/editor`, which `access.LocalAccess` covers along with the rest of the app (loopback or token, same-origin). Analysis job lookups need both the media id and the random job key (`_analysis`); a key from another file returns 404 (RUNTIME). Downloads are looked up by job key, and `index` is range-checked and limited to finished files (`editor_api.py:466-472`).

### Resource bounds

None detected:
- Analysis shares the single `processing` slot with uploads and exports. A busy slot returns 429 (RUNTIME), and the slot is released on every path, before the final status, so clients never see "done" while the slot is still held (RUNTIME).
- Cached results skip ffmpeg. Finished job records are pruned to 20 (`_forget_analyses`).
- Batch export accepts at most 50 ranges, each validated against the sequence before rendering starts (RUNTIME 422/400 cases). Cancel stops the whole batch.
- Subclips are capped at 500 per sequence.

### Client rendering (XSS)

None detected. There is no `{@html}`, `innerHTML` or `eval` in the editor sources. Labels, subclip names and moment reasons are rendered as text. Download URLs use the server's own job id and an integer index (`api.ts:60`).

### Secrets and environment

None detected. No new secrets, environment variables or network calls.

### Dependencies and supply chain

None detected. `package.json`, `package-lock.json`, `pyproject.toml` and `uv.lock` are unchanged against `origin/feature/editor`.

### Webhooks, headers, PII and logging

Not applicable or unchanged: no webhooks, no header changes, no new logging or telemetry.

## Re-evaluation

No Medium-or-higher finding needed a fix. After the Low fix, ruff, mypy, `tests/test_editor.py` (29 passed) and the full suite were rerun.

## Not checked

ffmpeg's own decoder hardening against malformed media, ffmpeg builds older than 9.0.2, LocalAccess internals, and fuzzing. No whole-application security claim is made.
