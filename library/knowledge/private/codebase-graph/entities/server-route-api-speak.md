---
type: entity
title: "POST /api/speak"
entity_type: function
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/server.py"
language: py
depends_on:
  - "[[entities/tts-speak]]"
  - "[[entities/audio-module]]"
used_by: []
tested_by: []
last_commit_hash: "0a207b37dc9809791194e8b796c9113351ebfb6e"
tags:
  - entity
  - cleanup
related:
  - "[[concepts/cleanup-processing-pipeline]]"
sources: []
---

# POST /api/speak

## Overview

Form endpoint that renders text to a WAV via [[entities/tts-speak]] (`src/naturalvoice/server.py:206-226`).

## Signature / Definition

```python
@app.post('/api/speak')
def speak(text, voice='af_heart', speed=1.0, engine='kokoro', humanize=True)
```

## Behavior

- 400 for empty text or over 20,000 characters (`server.py:216-219`) and for engine `RuntimeError`/`ValueError` (`:222-223`).
- Saves `speech-<uuid>.wav` under `WORK` and returns it as `natural-voice.wav` (`:224-226`). No caller found in the chunk's JS.

## Connections

- **depends_on:** [[entities/tts-speak]], [[entities/audio-module]]
- **used_by:** none found
- **related concepts:** [[concepts/cleanup-processing-pipeline]], [[concepts/cleanup-job-lifecycle]]

## Tested by

- none found

## History

- **Scan HEAD:** commit `0a207b3` (`dev`), 2026-10-18. Per-symbol git history not traced in this partial scan.

## Sources

- `src/naturalvoice/server.py` (lines 206-226)
