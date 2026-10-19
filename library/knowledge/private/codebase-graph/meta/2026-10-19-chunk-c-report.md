---
type: meta
title: "Chunk C run report (voices, Voice Lab, cloning, sample collections, isolated engines)"
created: 2026-10-19
updated: 2026-10-19
status: developing
tags:
  - meta
  - voices
---

# Chunk C run report

- Mode: `document`, `partial_scan: true`, repo HEAD `0a207b37dc9809791194e8b796c9113351ebfb6e` (`dev`).
- Parser: no tree-sitter, graph driver or Deep Lake here. Python outlines came from stdlib `ast` run read-only with the root venv interpreter; JS/HTML and shell were read as source (grep for API paths only). No stub pages: JS gets no entity pages in this run, it is referenced from API module pages.
- Prior state: the codebase-graph area did not exist; no contradictions; contradiction protocol not triggered.
- ADRs: none filed by instruction; concept pages link `docs/adr/0001-*` and `docs/adr/0004-*`.

## Pages (20)

17 entity pages under `entities/` (voices, voicelab, voicelab_api, clone, clone_api, chatterbox_worker, sample_library, sample_library_api, media_worker) and 3 concepts: `voices-voice-categories`, `voices-isolated-engines`, `voices-reference-versioning`. Over the 8 to 15 target because the owner asked for explicit engine boundary pages.

## Process boundary edges

- main app `clone._Worker` -> `engines/chatterbox/worker.py`: persistent JSON-lines subprocess (`src/naturalvoice/clone.py:136-189`).
- main app `sample_library.process_source` -> `engines/media/worker.py`: one-job subprocess (`src/naturalvoice/sample_library.py:231-241`).
- main app `sample_library.download` -> `engines/media/download.py` (yt-dlp), one-job (`sample_library.py:179-213`).

## Gaps

- Not covered as pages: `voicelab.describe`, `clone.convert`, `clone.speak_language`, `chatterbox Engine.speak/convert` internals, `scripts/download_media_models.py` (SHA-256 verified downloads, `:38-80`), web JS files.
- Links into chunk A/B (`server-module`, `studio-module`, `tts-module`, `audio-module`, `humanize-module`, `cli-module`, `llm-module`) depend on those chunks creating pages with these slugs.
