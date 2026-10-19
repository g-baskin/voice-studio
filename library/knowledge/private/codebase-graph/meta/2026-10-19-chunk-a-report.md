---
type: meta
title: "Chunk A scan report (cleanup, core, CLI, server shell)"
created: 2026-10-19
updated: 2026-10-19
status: developing
tags:
  - meta
---

# Chunk A scan report

- Repo: voice-studio, branch `dev`, HEAD `0a207b37dc9809791194e8b796c9113351ebfb6e`.
- Mode: `document`, `partial_scan: true`. No prior state and no contradictions.
- Extraction: Python was parsed with stdlib `ast` through the project venv interpreter (read-only). No tree-sitter, Hivemind graph driver or Deep Lake was available. JS and HTML were read as source, not AST-parsed.

## Pages written

22 pages (20 entities, 2 concepts) plus this report. That is above the 8-15 guideline because the chunk spans 15 files. Noted, not split further.

## Unresolved wikilinks (targets not written by this chunk)

- Owned by other chunks: `voices-catalog`, `voices-resolve`, `clone-speak`, `studio-cli-render`, `voicelab_api-router`, `studio_api-router`, `clone_api-router`, `sample_library_api-router`, `sample_library_api-sampleuploadlimit`, `rewrite_api-router`, `scriptgen_api-router`, `llm_api-router`.
- Chunk A targets not written (follow-up candidates): `cli-clean-file` (covered in `cli-main`), `quality-to-16k` and `tts-model-dir` (covered in `quality-dnsmos` and `tts-speak`), `web-index-html`, `tests-test-core`, `tests-test-workflow` (test files are also cited by path).

## Skipped

- `src/naturalvoice/__init__.py`: contains only `__version__ = "0.3.0"` (line 3), so no page.
- `web/index.html`: 353 lines, including an inline script at line 189. Not extracted beyond the `workflow.js` include (line 351).
- Private helpers (`_stft`, `_ffmpeg`, bench damage functions) are described only within their parent pages.

## Gaps

- The `sw.js` registration site was not found in this chunk.
- `POST /api/speak` has no caller in `workflow.js`. Other web pages are outside this chunk.

## Candidate decisions (for `docs/adr/`, not filed)

- Single-slot processing semaphore and in-memory job store (`server.py:29-31`).
- Apply the GTCRN gain mask to the full band instead of using its 16 kHz output (`enhance.py:5-7`).
- Reimplement the mel spectrogram in numpy to avoid librosa on Intel Macs (`quality.py:6-7`).
- Tune presets from `naturalvoice bench` findings (`humanize.py:40-43`).
- Register feature routers before the catch-all static mount (`server.py:229-245`).
