---
type: entity
title: "sample_library.process_source"
entity_type: function
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/sample_library.py"
language: py
depends_on:
  - "[[entities/sample_library-module]]"
  - "[[entities/media_worker-analyze]]"
used_by:
  - "[[entities/sample_library_api-module]]"
last_commit_hash: "0a207b37dc9809791194e8b796c9113351ebfb6e"
tested_by:
  - "tests/test_sample_library.py"
tags:
  - entity
  - voices
related: []
sources:
  - "src/naturalvoice/sample_library.py"
---

# sample_library.process_source

## Overview

Background pipeline for one imported source: optional download, ffmpeg window decode, then a one-job media-engine subprocess (`src/naturalvoice/sample_library.py:220-257`).

## Signature / Definition

```py
def process_source(key: str) -> None
```

## Behavior

- Downloads only when the record has a URL (`sample_library.py:224`); decodes to `original.wav` (`:228`).
- Spawns `engines/media/.venv/bin/python worker.py` with one JSON request on stdin, `timeout=900` (`:231-240`).
- Validates the result: duration in (0, 121], at most 2000 segments, each turn inside the duration with speaker < 100 (`:242-247`).
- On any failure records a generic error without subprocess output and keeps the source (`:249-256`).
- Progress steps published via `atomic_json` (`:226-230`, `:257`).
- Launched on a daemon thread by `launch`, which releases the server `processing` semaphore (`sample_library_api.py:104-112`, `server.py:31`).

## Connections

- **process boundary:** [[entities/media_worker-analyze]]
- **tested by:** `tests/test_sample_library.py:259` (failed analysis keeps source), `:247` (interrupted source and retry)
- **concepts:** [[concepts/voices-isolated-engines]]

## History

- **Last touched:** commit `0a207b3` (feat: add local voice sample collections) by AutomationGod on 2026-10-18, per `git log`.
