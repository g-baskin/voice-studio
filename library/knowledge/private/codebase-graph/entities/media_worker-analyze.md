---
type: entity
title: "media worker analyze (diarization)"
entity_type: function
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "engines/media/worker.py"
language: py
depends_on: []
used_by:
  - "[[entities/sample_library-process_source]]"
last_commit_hash: "0a207b37dc9809791194e8b796c9113351ebfb6e"
tested_by: []
tags:
  - entity
  - voices
related: []
sources:
  - "engines/media/worker.py"
---

# media worker analyze (diarization)

## Overview

One-job analysis in the isolated media engine: optional vocal separation, then sherpa-onnx speaker diarization on CPU (`engines/media/worker.py:65-104`). `main` reads one JSON line (max 8192 chars) and prints one JSON result (`worker.py:107-110`).

## Signature / Definition

```py
def analyze(path: Path, clean: bool, speakers: int) -> dict
```

## Behavior

- If `clean`, runs `separate` (Spleeter-style vocals ONNX, `worker.py:35-62`); always writes `dialogue.wav` beside the input (`:67-69`).
- Resamples to 16 kHz mono (`:70-71`); pyannote segmentation + speaker embedding models, fast clustering with fixed or automatic cluster count (`:72-84`).
- Emits `{duration, segments[{start, end, speaker, overlap}]}`; `overlap` flags any different-speaker intersection (`:89-104`).
- Model files from `scripts/download_media_models.py` (installed by `scripts/setup_media_engine.sh`, which is run explicitly, never by a web request).

## Connections

- **invoked by:** [[entities/sample_library-process_source]] (`sample_library.py:231-240`)
- **concepts:** [[concepts/voices-isolated-engines]]
- **ADR:** `docs/adr/0004-isolate-media-analysis-and-version-references.md`

## History

- **Last touched:** commit `0a207b3` (feat: add local voice sample collections) by AutomationGod on 2026-10-18, per `git log`.
