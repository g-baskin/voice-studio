---
type: concept
title: "Isolated engines: Chatterbox (persistent) and media (one-job)"
complexity: intermediate
domain: voices
aliases: []
created: 2026-10-19
updated: 2026-10-19
status: developing
tags:
  - concept
  - voices
related:
  - "[[entities/clone-_Worker]]"
  - "[[entities/chatterbox_worker-main]]"
  - "[[entities/media_worker-analyze]]"
  - "[[entities/sample_library-process_source]]"
sources: []
---

# Isolated engines: Chatterbox (persistent) and media (one-job)

## Definition

Two optional engines run in their own Python environments so the root ONNX Runtime pin (1.19.2) stays intact. See `docs/adr/0001-isolate-the-cloning-engine.md` and `docs/adr/0004-isolate-media-analysis-and-version-references.md`.

## Process boundary edges

| Edge | Style | Evidence |
|---|---|---|
| main app [[entities/clone-_Worker]] -> `engines/chatterbox/worker.py` [[entities/chatterbox_worker-main]] | **persistent** subprocess, JSON lines on stdin/stdout, request ids, ready message id 0, idle shutdown (600 s default) | `clone.py:136-146`, `:173-189`, `:161-171`; `worker.py:126-162` |
| main app [[entities/sample_library-process_source]] -> `engines/media/worker.py` [[entities/media_worker-analyze]] | **one-job** subprocess: one JSON request on stdin, one JSON result on stdout, 900 s timeout | `sample_library.py:231-241`; `worker.py:107-110` |
| main app `sample_library.download` -> `engines/media/download.py` (yt-dlp) | one-job subprocess, CLI args, 300 s timeout, 250 MB file-size rlimit | `sample_library.py:179-213`; `download.py:7-8` |

Audio crosses the boundary as file paths (WAV in, `.npy` or WAV out), never as inline payloads (`engines/chatterbox/worker.py:3-7`; `engines/media/worker.py:69`).

## Why it matters

- Merging engine dependencies into the root environment breaks Intel-Mac wheels (AGENTS.md).
- The parent must validate engine output: `process_source` bounds duration and timelines (`sample_library.py:242-247`); `_Worker` kills the child on timeout or EOF (`clone.py:115-121`).
- Setup is explicit: `scripts/setup_clone_engine.sh`, `scripts/setup_media_engine.sh` (`setup_media_engine.sh:2-6`).

## Connections

- [[concepts/voices-voice-categories]], [[concepts/voices-reference-versioning]]
