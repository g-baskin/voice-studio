# QA report: Editor Clip mode (feature/clip-mode)

**Plan:** `.gg/plans/editor-clip-mode.md` (main checkout), approved.
**Candidate:** uncommitted worktree `feature/clip-mode` on `origin/feature/editor` (117000a).
**Ordering:** the Security review (`2026-11-05-clip-mode-security.md`) ran first. The fixes below change editing logic only. They add no endpoints, ffmpeg calls or file paths, so that review still holds.
**Reviewers:** the implementing agent, plus two independent read-only reviewers (frontend edit logic; backend and tests).

## Summary

Every in-scope plan item is implemented and covered by tests. The review found two Critical issues and several Warnings, all fixed in this pass with regression checks:
- **Silence removal** cut clips that were not silent.
- **Reverse shuttle** from the very end stopped at once (found while re-running the browser check).

Verdict: ready for the owner's ship decision.

## Scorecard

| Axis | Status |
| --- | --- |
| Completeness | Pass. All ten in-scope items are built. The out-of-scope items (transcripts, face tracking, LLM ranking) are left out, as the plan says. |
| Correctness | Pass after fixes (see below). |
| Alignment | Pass. One document model shared by Edit and Clip; existing conventions (commit/gesture undo, `processing` slot, `INPUT_GUARD`, `_filename`). |
| Gaps | Small items remain, listed under Suggestions. |
| Detrimental patterns | None found. No new dependencies; no placeholders or skipped tests. |

## Critical issues (fixed)

1. **Silence removal cut non-silent clips.** The old `removeSilences` in `frontend/src/lib/editor/editor.svelte.ts` merged spans from every clip of the media and cut them on every track holding that media. A second clip of the same file at another offset was cut where it was not silent.
   - **Fix:** `silenceCuts` (`timeline.ts`) now returns `[start, end, tracks]`. A span is cut only from tracks whose own clip is silent across it, and linked copies (same media, offset and speed) are included through `linkedClips`. As with ripple delete, each cut closes up only its own tracks.
   - **Regression check:** `tests/browser_editor.cjs`, where a V2 clip of the same file stays whole, plus pure-function checks.
2. **Reverse shuttle from the end stopped at once.** In `Preview.svelte` and `SourceMonitor.svelte` `tick`, an animation frame's timestamp can be earlier than `startedAt`. Reversing from the last frame then computed a time past the end and paused.
   - **Fix:** elapsed time is clamped at zero.
   - **Regression check:** the browser check now reverses from End.

## Warnings (fixed)

- **Unused track added.** `patched()` resolved both target kinds, so `firstTrack` could add an unused audio track inside a picture edit. It now resolves only the kind the edit uses.
- **Reverse three-point with a short source.** With only a source Out shorter than the sequence span, the clip did not end on the sequence Out. `threePoint` now keeps the end on the sequence Out.
- **Empty undo steps.** `commit` recorded an undo step even when nothing changed (an empty lift, Q/W in a gap). It now skips unchanged edits, the way `endGesture` already does.
- **Keys:**
  - K release with Option held left `holdingK` set; release is now also matched on `e.code`.
  - Key repeat raced J/L to 8×; repeats are now ignored.
  - On layouts that type `;` with Shift (German Shift+,), that press ran Lift. Lift and Extract now need an unshifted key.
- **Moment snapping broke limits.** Snapping to pauses ran after the overlap check and could break the length limits and the no-overlap rule (`editor.py` `score_moments`). Snapping now happens before the overlap check and is kept only within the limits. Regression: `test_moments_snapped_to_pauses_keep_their_length_limits_and_never_overlap` fails on the old code and passes on the new.
- **Stale analysis cache.** Cache keys had no version. They now include `ANALYSIS_VERSION`, so changes to detection or scoring retire old results.

## Suggestions (not changed)

- **Delete/analysis race.** There is a small window between `analysis_start`'s media check and its job registration in which `media_delete` could run. The worst case is an orphan analysis file (the Low finding in the Security report).
- **Non-QWERTY keys.** Shortcuts other than Option combinations follow the typed character, so some keys move or go missing on non-QWERTY layouts. The menus offer every action.
- **Cancel response time.** Cancelling an analysis is noticed on ffmpeg's next progress line (about every 0.5 s), not instantly.

## Plan item traceability

| Plan item | Where | Evidence |
| --- | --- | --- |
| Edit/Clip mode, localStorage + `?mode=clip` | `+page.svelte` `setMode`, `editor.savedMode` | browser: switch, URL, reload |
| Source viewer: load, scrub, I/O, Alt+X, X, V/A | `SourceMonitor.svelte`, `MediaBin.svelte` | browser: Enter loads; marks; Alt+X |
| Insert/overwrite/append/smart, reverse three-point, targets, lift/extract | `timeline.ts` `threePoint`, `insertEdit`, `overwriteEdit`, `liftRange`, `extractRange`; store `sourceEdit` | browser: lengths and clip layout; scratch `check.mts` |
| J/K/L shuttle, K+J/L step, ←/→ frames | `+page.svelte` keys, `Preview.svelte`, `player.ts` | browser: ▶ 2×, ◀ 2×, K stops |
| Ripple/roll/slide tools, Q/W, Alt+Q/W, E | `timeline.ts` `rippleEdge`, `rollEdit`, `slideClip`, `trimToPlayhead`, `extendEdge`; `Timeline.svelte` | browser: layouts after each drag, Q/W lengths |
| Dual-frame trim view | `Preview.svelte`, `player.ts` | browser: Outgoing/Incoming labels; screenshot |
| Subclips, marker colours, marker list | `editor.py` `Subclip`; `ClipPanel.svelte` | pytest subclip tests; browser: Cmd/Ctrl+U |
| Silence and scene detection jobs | `editor.py` `detect_*`; `editor_api.py` analysis routes | pytest on real media; browser removal and scenes |
| Moments finder, honest label | `editor.py` `score_moments`; `ClipPanel.svelte` | pytest ranking and snapping; browser label |
| 16:9 / 9:16 / 1:1, reframe | `Preview.svelte`, `ReframeOverlay.svelte` | browser: vertical canvas, x 0.25, undo |
| Batch export | `editor_api.py` `ranges`, `ExportDialog.svelte` | pytest batch; browser: two files, second 6 s |
| Docs and changelog | `docs/editor-clip-mode.md`, `CHANGELOG.md` | written; claims checked against code |

## Files changed

- `src/naturalvoice/editor.py`: subclips, marker colours, analysis, moments, versioned cache.
- `src/naturalvoice/editor_api.py`: analysis jobs, batch export, per-file download, delete guard.
- `frontend/src/lib/editor/{types,timeline,api,player,editor.svelte}.ts`: models, pure edits, store.
- `frontend/src/routes/editor/`: `+page.svelte`, `Preview`, `Timeline`, `MediaBin`, `ExportDialog`, plus the new `SourceMonitor`, `ClipPanel` and `ReframeOverlay`.
- `tests/test_editor.py`, `tests/browser_editor.cjs`: new checks.
- `src/naturalvoice/ui/**` and the code graph: regenerated.

## Check receipts (this candidate)

- `npm run check`: exit 0 (format, lint, mypy, tsc, svelte-check 0/0, UI build current).
- `uv run --locked pytest -q`: 270 passed, 6 skipped. The skips need the clone engine, media models or GTCRN, none installed here.
- `tests/browser_editor.cjs` against a fresh server (port 8778, disposable data), light and dark: passed.
- `uv build`: passed after the review fixes and docs.
