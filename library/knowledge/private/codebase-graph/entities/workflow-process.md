---
type: entity
title: "workflow.process (Clean job body)"
entity_type: function
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/workflow.py"
language: py
depends_on:
  - "[[entities/audio-module]]"
  - "[[entities/analyze-report]]"
  - "[[entities/humanize-humanize]]"
  - "[[entities/workflow-recommend]]"
used_by:
  - "[[entities/server-route-api-clean]]"
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

# workflow.process (Clean job body)

## Overview

Runs one Clean operation (`clean`, `preview` or `analyze`) on an uploaded file and returns before/after reports, warnings and loudness-matched comparison copies (`src/naturalvoice/workflow.py:138-173`).

## Signature / Definition

```python
def segment(src, dst, start, seconds) -> tuple[np.ndarray, int]
def recommend(data, sr) -> dict
def warnings(before, after, room_tone) -> list[str]
def matched_copies(before, after, sr) -> tuple[np.ndarray, np.ndarray, dict]
def process(src, dst, settings, mode, start, seconds, progress) -> dict
```

## Behavior

- `preview`/`analyze` cut a section via ffmpeg `segment` (`workflow.py:139-140`, `:14-44`); `clean` loads the whole file (`:142`).
- Rejects audio under 0.1 s or non-finite (`:143-144`).
- `analyze` returns only an advisory `recommend` suggestion, no output file (`:145-146`).
- Otherwise reports before, runs `hz.humanize`, remuxes video or saves audio (`:148-153`), then re-loads and scores the actual export (`:155-157`).
- Writes `compare-before.wav` and `compare-after.wav` from `matched_copies` (`:160-163`).

## Connections

- **depends_on:** [[entities/audio-module]], [[entities/analyze-report]], [[entities/humanize-humanize]], [[entities/workflow-recommend]]
- **used_by:** [[entities/server-route-api-clean]]
- **related concepts:** [[concepts/cleanup-processing-pipeline]], [[concepts/cleanup-job-lifecycle]]

## Tested by

- `tests/test_workflow.py`

## History

- **Scan HEAD:** commit `0a207b3` (`dev`), 2026-10-18. Per-symbol git history not traced in this partial scan.

## Sources

- `src/naturalvoice/workflow.py` (lines 14-173)
