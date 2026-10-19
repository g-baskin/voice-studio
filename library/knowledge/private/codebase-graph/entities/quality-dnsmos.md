---
type: entity
title: "quality module (DNSMOS, PESQ, to_16k)"
entity_type: module
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/quality.py"
language: py
depends_on:
  - "[[entities/tts-module]]"
used_by:
  - "[[entities/analyze-report]]"
  - "[[entities/bench-run]]"
  - "[[entities/enhance-ai-clean]]"
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

# quality module (DNSMOS, PESQ, to_16k)

## Overview

Research-standard speech-quality scores: DNSMOS (reference-free), wideband PESQ and the shared 16 kHz resampler (`src/naturalvoice/quality.py:1-10`). Librosa's mel spectrogram is reimplemented in numpy because librosa cannot install on Intel Macs (`:6-7`).

## Signature / Definition

```python
def to_16k(x, sr) -> np.ndarray
def melspec_db(audio, n_mels=120, frame_size=320, hop=160, sr=SR) -> np.ndarray
def dnsmos(x, sr) -> dict
def pesq_wb(ref, y, sr) -> float | None
```

## Behavior

- `to_16k` resamples with `resample_poly` (`quality.py:27-33`).
- DNSMOS sessions are `lru_cache`d and raise `RuntimeError` if model files are missing (`:83-93`); scoring pads to `INPUT_LENGTH` 9.01 s windows (`:23`, `:96-122`).
- `pesq_wb` returns `None` when not computable (`:128-134`).

## Connections

- **depends_on:** [[entities/tts-module]]
- **used_by:** [[entities/analyze-report]], [[entities/bench-run]], [[entities/enhance-ai-clean]]
- **related concepts:** [[concepts/cleanup-processing-pipeline]], [[concepts/cleanup-job-lifecycle]]

## Tested by

- `tests/test_workflow.py`

## History

- **Scan HEAD:** commit `0a207b3` (`dev`), 2026-10-18. Per-symbol git history not traced in this partial scan.

## Sources

- `src/naturalvoice/quality.py` (lines 1-134)
