---
type: entity
title: "enhance.ai_clean (GTCRN neural cleanup)"
entity_type: function
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/enhance.py"
language: py
depends_on:
  - "[[entities/quality-dnsmos]]"
  - "[[entities/tts-module]]"
used_by:
  - "[[entities/humanize-humanize]]"
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

# enhance.ai_clean (GTCRN neural cleanup)

## Overview

Optional neural cleanup using the GTCRN ONNX model; reads the 16 kHz gain mask and applies it to the full-band original so voices are not muffled (`src/naturalvoice/enhance.py:1-8`).

## Signature / Definition

```python
def available() -> bool
def gain_mask(x, sr) -> tuple[np.ndarray, np.ndarray, np.ndarray]
def ai_clean(x, sr, amount: float, floor_db: float = -20.0) -> np.ndarray
```

## Behavior

- `available()` checks `MODEL_DIR/gtcrn_simple.onnx` exists (`enhance.py:25-26`); the ONNX session is cached with `lru_cache(maxsize=1)` (`:29-39`).
- `ai_clean` returns input unchanged when `amount <= 0` (`:68-70`), then interpolates the mask over a full-band STFT (`:71-92`).
- Imports `to_16k` from quality and `MODEL_DIR` from tts (`:18-19`).

## Connections

- **depends_on:** [[entities/quality-dnsmos]], [[entities/tts-module]]
- **used_by:** [[entities/humanize-humanize]], [[entities/bench-run]]
- **related concepts:** [[concepts/cleanup-processing-pipeline]], [[concepts/cleanup-job-lifecycle]]

## Tested by

- none found

## History

- **Scan HEAD:** commit `0a207b3` (`dev`), 2026-10-18. Per-symbol git history not traced in this partial scan.

## Sources

- `src/naturalvoice/enhance.py` (lines 1-92)
