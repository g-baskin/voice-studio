---
type: entity
title: "tts.speak (engine dispatch)"
entity_type: function
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/tts.py"
language: py
depends_on:
  - "[[entities/voices-module]]"
  - "[[entities/clone-module]]"
  - "[[entities/humanize-humanize]]"
  - "[[entities/humanize-settings]]"
used_by:
  - "[[entities/server-route-api-speak]]"
  - "[[entities/cli-main]]"
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

# tts.speak (engine dispatch)

## Overview

Synthesizes text with Kokoro, the cloning engine, ElevenLabs or OpenAI, pads silence and optionally runs the light cleanup preset (`src/naturalvoice/tts.py:113-148`). The module also defines `MODEL_DIR` from `NATURALVOICE_MODELS` (`:22`).

## Signature / Definition

```python
def speak(text, voice='af_heart', speed=1.0, engine='kokoro', humanize=True,
          settings: hz.Settings | None = None) -> tuple[np.ndarray, int]
```

## Behavior

- A `clone:` voice id with engine kokoro switches to the clone engine (`tts.py:121-122`); missing clone module raises `RuntimeError` (`:123-128`).
- Kokoro path `speak_kokoro` resolves the voice vector through `vlib.resolve` (`:72-75`) and splits text by punctuation pauses (`:25`, `:44-68`).
- Cloud engines need `ELEVENLABS_API_KEY` / `OPENAI_API_KEY` env vars (`:132-140`); unknown engine raises `ValueError` (`:142`).
- Adds 0.15 s lead and 0.30 s tail silence, then `hz.humanize` with `get_settings("light")` by default (`:144-147`).

## Connections

- **depends_on:** [[entities/voices-module]], [[entities/clone-module]], [[entities/humanize-humanize]], [[entities/humanize-settings]]
- **used_by:** [[entities/server-route-api-speak]], [[entities/cli-main]], [[entities/bench-run]]
- **related concepts:** [[concepts/cleanup-processing-pipeline]], [[concepts/cleanup-job-lifecycle]]

## Tested by

- none found

## History

- **Scan HEAD:** commit `0a207b3` (`dev`), 2026-10-18. Per-symbol git history not traced in this partial scan.

## Sources

- `src/naturalvoice/tts.py` (lines 22-148)
