---
type: entity
title: "POST /api/clean"
entity_type: function
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/server.py"
language: py
depends_on:
  - "[[entities/humanize-settings]]"
  - "[[entities/audio-module]]"
  - "[[entities/workflow-process]]"
used_by:
  - "[[entities/web-workflow-module]]"
tested_by:
  - "tests/test_workflow.py"
last_commit_hash: "0a207b37dc9809791194e8b796c9113351ebfb6e"
tags:
  - entity
  - cleanup
related:
  - "[[concepts/cleanup-processing-pipeline]]"
sources: []
---

# POST /api/clean

## Overview

Accepts an upload plus cleanup preset and control overrides, validates, stores it, and starts a background Clean job (`src/naturalvoice/server.py:58-141`).

## Signature / Definition

```python
@app.post('/api/clean')
async def clean(file: UploadFile, preset='standard', ai_clean..room_tone: str = None,
                mode='clean', start: float = 0, seconds: float = 15) -> {'job': str}
```

## Behavior

- Controls must be finite 0..1 or 400 (`server.py:34-38`, `:84-85`); mode in clean/preview/analyze, start 0..86400 (`:86-87`); seconds 10..20 (`:88-89`).
- Allowed suffixes: `VIDEO_EXTS` plus common audio types (`:90-92`).
- 429 if the semaphore is held (`:93-94`); streams 1 MiB chunks, 413 over 500 MB, 400 if empty, cleans up on failure (`:98-114`).
- Background thread calls [[entities/workflow-process]] and updates `jobs[job]` progress, result or a sanitised public error (`:118-140`).

## Connections

- **depends_on:** [[entities/humanize-settings]], [[entities/audio-module]], [[entities/workflow-process]]
- **used_by:** [[entities/web-workflow-module]]
- **related concepts:** [[concepts/cleanup-processing-pipeline]], [[concepts/cleanup-job-lifecycle]]

## Tested by

- `tests/test_workflow.py`

## History

- **Scan HEAD:** commit `0a207b3` (`dev`), 2026-10-18. Per-symbol git history not traced in this partial scan.

## Sources

- `src/naturalvoice/server.py` (lines 34-141)
