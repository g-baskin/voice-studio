# QA Report: Shorts captions-first clipping workflow

**Plan document:** `/Users/dellcbyerllc/projects/voice-studio/.gg/plans/shorts-captions.md`
**Audit date:** 2026-11-05
**Base branch:** `origin/feature/svelte-pages` (7719a6c)
**Head:** `feature/shorts-captions`, uncommitted working tree on 7719a6c
**Auditor:** quality-wasp-drone (read-only)
**Candidate scope:** `git status --short` + `git diff` + untracked files in the worktree; generated `src/naturalvoice/ui/**`, code graph, `models` symlink and node_modules excluded. No manifest digest was made, so this report applies to the tree as it was on 2026-11-05.
**Security evidence:** `library/requirements/reports/editor/2026-11-05-shorts-captions-security.md` (0 C/H/M, 3 Low fixed). The order was correct: Security ran before QA.
**Claim boundary:** This is a static source review plus targeted local checks. Full-suite, browser and build results come from the implementer and were not rerun here.

## Summary

**Pass with warnings.** Everything in plan steps 1–19 is built. The Python and TS paging code match line for line, the timeline mapping is correct, cleanup edits are one undo step each, and the overwrite guard and 30-minute cap are enforced in two layers. There are no Critical issues. The two Warnings are accessibility gaps in the Transcript word list: editing a word and selecting a range both need a mouse. Steps 20 (docs) and 21 (ship question) are pending by design.

## Scorecard

| Category | Status | Notes |
|---|---|---|
| Completeness | ✅ | Steps 1–19 implemented; 20–21 pending by design |
| Correctness | ✅ | Paging, mapping, undo, guard and cap verified in source |
| Alignment | ⚠️ | Hooks UI defaults to 60 s, plan says 15–90 s |
| Gaps | ⚠️ | Keyboard access for word edit and range select |
| Detrimental | ✅ | No new ffmpeg features; worker output validated; LLM path is opt-in |

## Critical Issues

None.

## Warnings

- [ ] **Word text can only be fixed by double-click**, `frontend/src/routes/editor/TranscriptPanel.svelte:205-213`
  `ondblclick={() => startEdit(i)}` is the only way into edit mode, so keyboard and screen-reader users cannot fix a word. Add a key such as Enter/F2 on a focused word, or an "Edit" action. (WCAG 2.1.1)
- [ ] **Range selection needs Shift+mouse-click**, `TranscriptPanel.svelte:73-76`
  `if (e.shiftKey && anchor !== null) focus = i` reads the modifier from a click event. A click fired by the keyboard (Enter/Space) normally has `shiftKey` false, so keyboard users can only select one word at a time before Delete. Add Shift+Arrow or Shift+Enter range extension.

## Suggestions

- [ ] **400 tab stops per word page**, `TranscriptPanel.svelte:187-216`: every word is a `<button>` in the tab order. Use roving tabindex with arrow keys.
- [ ] **TS parity covers only fixture case 0 of 2**, `tests/browser_editor.cjs:516-633`: Python checks every case (`tests/test_captions.py:38`). Run the second case in the browser too, or add a node unit check of `captions.ts` `pages()`.
- [ ] **Hooks longest default is 60 s**, `frontend/src/routes/editor/HooksPanel.svelte:10`: the plan and backend use 15–90 s (`transcript.py:358`, `editor_api.py` HookRequest). Align the UI default or note the choice.
- [ ] **Dangling `aria-describedby`**, `frontend/src/routes/editor/CaptionsPanel.svelte` (track select): `caption-track-note` does not exist when no note is shown. Only add the attribute when the note renders.
- [ ] **Doc comment doesn't match code**, `frontend/src/lib/editor/editor.svelte.ts` `transcriptClips`: the comment says "its chosen clips, else all", but the code uses every unlocked clip of the media. Fix the comment or the behaviour.
- [ ] **Unplanned playback change**, `frontend/src/routes/editor/Preview.svelte` `(rate > 0 && t >= end) || ...`: this reverse-playback fix is outside the plan. Mention it in the PR/CHANGELOG.
- [ ] **Preview font when the font file is missing**: the preview falls back to `sans-serif` (`editor.svelte.ts` loadFont catch) and the export to Pillow's `load_default` (`captions.py:253`). Layout can drift on machines without the allowlisted fonts. This limit is stated in the plan; document it in docs/editor-shorts.md.

## Focus checks

- **Paging parity:** `captions.py:114-132` and `captions.ts:69-89` use the same rules (per-page limit, 0.6 s gap, terminal punctuation with closing quotes stripped, code-point char count `len`/`[...s].length`, 0.3 s hold clipped to the next page, `r3` rounding). Both sides use the shared fixture `tests/fixtures/caption_pages.json`.
- **timeline_words:** `captions.py:96-107` and `captions.ts:53-66` are identical. Words are kept when their centre falls in `[source_in, source_out)`, ends are clamped and mapped as `start + (t - source_in)/speed`, and muted clips and muted tracks are skipped. Tested at `tests/test_captions.py:46` (speed, trim, mute, cut).
- **Undo granularity:** `removeWords`, `shortenPauses`, `removeFillers` and `removeSilences` each make one `rippleCuts` → one `commit` (`editor.svelte.ts` rippleCuts). `setCaptions` is one commit.
- **Overwrite guard:** the API returns 409 (`editor_api.py` transcript_start), `tr.transcribe` re-checks (`transcript.py:233-235`), and the UI asks `confirm()` then sends `overwrite` (`TranscriptPanel.svelte:112-115`). Saving while a transcription runs returns 409.
- **30-minute cap:** the export pre-checks (`captions.check_export`, `editor_api.py` export_start), `render_frames` (`captions.py:266`) also enforces it, and states are capped at 5,000 (`captions.py:292`). The frames folder is removed in `finally` (`editor.py` render).
- **Hooks / LLM:** windows are sentence-bounded, scores are relative 0–100, overlaps are suppressed and there is a work budget (`transcript.py:353-455`). AI ranking runs only when `use_ai` is set and `llm.config()` exists (400 otherwise); it sends at most 20×160 chars, parses ids only and falls back on bad replies (`transcript.py:465-487`). The UI names the provider and only shows the AI button when a provider is configured (`HooksPanel.svelte:82-92`).
- **Accessibility:** tabs keep roving focus. The new controls are labelled: progress, switch role, fieldset/legend, `aria-pressed` style buttons, and labelled Listen/Hook buttons. `#caption-now` is present with `aria-live="off"`. Gaps are listed under Warnings.

## Plan Item Traceability

| # | Plan Requirement | Status | Location | Notes |
|---|---|---|---|---|
| 1 | Worktree + baseline | ✅ | worktree | implementer-reported |
| 2 | Owner approvals | ✅ | pyproject.toml:20 pillow | approval record not inspected |
| 3 | Downloader + setup script, pinned sizes/SHA, ATTRIBUTION | ✅ | scripts/download_speech_model.py:11-63, setup_speech_model.sh | tokens.txt SHA-256 pinned |
| 4 | transcribe.py pure functions + tests + lint paths | ✅ | engines/media/transcribe.py; tests/test_media_engine.py:57-76; package.json:5-7 | 4 h refusal at transcribe.py:16-25 |
| 5 | Real model fields | 🟦 | — | integration test skips without model (test_transcript.py:212) |
| 6 | Captions model + Sequence.captions + types | ✅ | editor.py:153-219; types.ts | old sequences load (test_editor.py:560) |
| 7 | transcript.py functions + fake-worker tests | ✅ | transcript.py; tests/test_transcript.py | |
| 8 | captions.py + fixture + tests | ✅ | captions.py; tests/test_captions.py | |
| 9 | build_command/render caption input + pixel test | ✅ | editor.py:712-720, 785-807; test_editor.py:582,596 | |
| 10 | Endpoints + delete guard + API tests | ✅ | editor_api.py:301-476, 193 | |
| 11 | captions.ts + api.ts | ✅ | captions.ts; api.ts | |
| 12 | Store actions, player draw, #caption-now | ✅ | editor.svelte.ts; player.ts:228; Preview.svelte | |
| 13 | Three panels, tabs, burn-in option | ⚠️ | Transcript/Captions/HooksPanel, ClipPanel, ExportDialog | keyboard Warnings |
| 14 | T / Shift+C keys, menu, shortcut list | ✅ | +page.svelte:299-313, 482-488, 542 | `t` was unused at base |
| 15–17 | Format, svelte-check, build, pytest | ✅ | — | implementer-reported (306 passed / 6 skipped; npm run check) |
| 16 | Browser checks light+dark | ✅ | tests/browser_editor.cjs:515+ | implementer-reported, port 8779 |
| 18 | Security review | ✅ | security report | |
| 19 | Final QA | ✅ | this report | |
| 20 | docs/editor-shorts.md, README, CHANGELOG, clip-mode link | 🟦 | — | pending by design |
| 21 | Report + commit/PR question | 🟦 | — | pending by design |
| NG | Out of scope (reframe, split-screen, B-roll, emoji, speaker colours) | ✅ | — | not introduced |

## Verification

- Run by QA: `uv run --locked pytest tests/test_captions.py tests/test_transcript.py -q` → 26 passed; `uv run --locked ruff check src engines/media/transcribe.py scripts/download_speech_model.py` → passed.
- Implementer-reported, not rerun: full pytest, `npm run check`, browser_editor.cjs, `uv build`.
- Not checked: real model transcription, screenshots, Linux font paths, `uv build`.

## Files Changed

engines/media/transcribe.py (A), frontend/src/lib/editor/{api,editor.svelte,player,types}.ts (M), frontend/src/lib/editor/captions.ts (A), frontend/src/routes/editor/{+page,ClipPanel,ExportDialog,Preview}.svelte (M), frontend/src/routes/editor/{Captions,Hooks,Transcript}Panel.svelte (A), package.json (M), pyproject.toml (M), scripts/download_speech_model.py (A), scripts/setup_speech_model.sh (A), src/naturalvoice/{captions,transcript}.py (A), src/naturalvoice/{editor,editor_api}.py (M), tests/browser_editor.cjs (M), tests/fixtures/caption_pages.json (A), tests/test_{captions,transcript}.py (A), tests/test_{editor,media_engine}.py (M), uv.lock (M).

## Resolution (2026-11-05, after the Quality review and the read-only reviewer pass)

The read-only reviewer pass (skeptic) confirmed 3 more bugs. All findings below were re-opened in the code, then fixed.

### Warnings from this review

- **W1 and W2, keyboard editing and selection** (`TranscriptPanel.svelte`): fixed.
  - The word list now uses a roving tabindex, so only one word is a Tab stop. This also covers the 400-tab-stops Suggestion.
  - ArrowLeft, ArrowRight, Home and End move between words, and Shift with an arrow key extends the selection.
  - F2 edits the focused word. The edit box takes focus when it opens, Enter saves and Escape cancels. The hint text was updated to match.
  - Browser check added: click, then Shift+ArrowRight twice, gives "Cut 3 words", focus lands on the right word, and F2 opens a focused edit box.

### Bugs from the reviewer pass

- **Reviewer Medium: removing the caption track broke saving** (`editor.svelte.ts` `removeTrack`): fixed.
  - Removing the track that captions follow now resets `captions.track` to `null` in the same undo step.
  - Browser check added: add an audio track, set captions to follow it, remove it in Edit mode, then confirm the sequence still saves and the select shows "First track with sound".
- **Reviewer Low: the extra-fillers setting fell out of step with the list** (`TranscriptPanel.svelte`, `editor.svelte.ts` `loadTranscript`): fixed.
  - The setting now lives on the editor as `extraFillers`, and every transcript load uses it.
- **Reviewer Low: a forced reload during a load was skipped** (`editor.svelte.ts` `loadTranscript`): fixed.
  - A forced reload requested while a load is in flight is now queued and runs once that load ends.

### Suggestions

- **Applied:**
  - The "Longest" hook length now defaults to 90 s, matching the plan.
  - The track select only sets `aria-describedby` when the note is shown.
  - The `transcriptClips` comment was corrected.
- **Left as is:**
  - **Browser parity check uses fixture case 0 only.** The Python tests cover both cases, and the TS paging rules were statically matched.
  - **Preview reverse-stop change.** It will be noted in CHANGELOG (step 20).
  - **Font fallback drift.** It will be documented in `docs/editor-shorts.md` (step 20).

### Reruns

- `npm run check`: see the workflow record.
- Browser: `tests/browser_editor.cjs` passed on a fresh server on port 8779 with fresh `NATURALVOICE_DATA`, in light and dark.
