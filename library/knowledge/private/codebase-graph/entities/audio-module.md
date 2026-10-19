---
type: entity
title: "audio module (load, save, remux)"
entity_type: module
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/audio.py"
language: py
depends_on: []
used_by:
  - "[[entities/workflow-process]]"
  - "[[entities/cli-main]]"
  - "[[entities/server-app]]"
  - "[[entities/bench-run]]"
tested_by: []
last_commit_hash: "0a207b37dc9809791194e8b796c9113351ebfb6e"
tags:
  - entity
  - cleanup
related:
  - "[[concepts/cleanup-processing-pipeline]]"
sources: []
---

# audio module (load, save, remux)

## Overview

ffmpeg and soundfile wrappers for decoding, encoding and remuxing audio into video (`src/naturalvoice/audio.py:1-84`).

## Signature / Definition

```python
VIDEO_EXTS = {'.mp4', '.mov', '.mkv', '.webm', '.avi', '.m4v'}
def is_video(path) -> bool
def load(path, sr: int | None = None) -> tuple[np.ndarray, int]
def save(path, audio, sr) -> None
def remux_video(video_in, audio, sr, video_out) -> None
```

## Behavior

- `_ffmpeg` raises `RuntimeError` if ffmpeg is not on PATH (`audio.py:20-24`).
- `load`/`save` route through ffmpeg for formats soundfile cannot handle (`:27-52`).
- `remux_video` writes a temp WAV and muxes it with the unchanged picture (`:55-84`).
- `VIDEO_EXTS` gates accepted uploads in `/api/clean` (`src/naturalvoice/server.py:91`).

## Connections

- **depends_on:** none in chunk
- **used_by:** [[entities/workflow-process]], [[entities/cli-main]], [[entities/server-app]], [[entities/bench-run]]
- **related concepts:** [[concepts/cleanup-processing-pipeline]], [[concepts/cleanup-job-lifecycle]]

## Tested by

- none found

## History

- **Scan HEAD:** commit `0a207b3` (`dev`), 2026-10-18. Per-symbol git history not traced in this partial scan.

## Sources

- `src/naturalvoice/audio.py` (lines 1-84)
