---
type: entity
title: "humanize.humanize and process_mono"
entity_type: function
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/humanize.py"
language: py
depends_on:
  - "[[entities/humanize-settings]]"
  - "[[entities/enhance-ai-clean]]"
used_by:
  - "[[entities/workflow-process]]"
  - "[[entities/cli-main]]"
  - "[[entities/tts-speak]]"
  - "[[entities/bench-run]]"
tested_by:
  - "tests/test_core.py"
last_commit_hash: "0a207b37dc9809791194e8b796c9113351ebfb6e"
tags:
  - entity
  - cleanup
related:
  - "[[concepts/cleanup-processing-pipeline]]"
sources: []
---

# humanize.humanize and process_mono

## Overview

Entry point of the cleanup chain: runs eight stages in fixed order on mono audio, handling stereo via mid/side (`src/naturalvoice/humanize.py:332-368`).

## Signature / Definition

```python
def process_mono(x, sr, s: Settings, progress=None) -> np.ndarray
def humanize(audio, sr, settings: Settings | None = None, progress=None) -> np.ndarray
```

## Behavior

- Stage order: AI cleanup (only if `ai_clean > 0` and `enhance.available()`), echo removal, metallic tone, harshness, artifacts, warmth, room tone, loudness (`humanize.py:335-344`).
- Reports `progress(name, i/len(steps))` before each stage and `("Done", 1.0)` at the end (`:346-351`).
- `humanize` defaults to `Settings()` (`:357`); mono or single-channel input goes straight to `process_mono` (`:358-361`).
- Stereo: processes the mid channel, rescales side by mid gain times 0.5, clips to +-0.99 (`:363-368`).

## Connections

- **depends_on:** [[entities/humanize-settings]], [[entities/enhance-ai-clean]]
- **used_by:** [[entities/workflow-process]], [[entities/cli-main]], [[entities/tts-speak]], [[entities/bench-run]]
- **related concepts:** [[concepts/cleanup-processing-pipeline]], [[concepts/cleanup-job-lifecycle]]

## Tested by

- `tests/test_core.py`

## History

- **Scan HEAD:** commit `0a207b3` (`dev`), 2026-10-18. Per-symbol git history not traced in this partial scan.

## Sources

- `src/naturalvoice/humanize.py` (lines 332-368)
