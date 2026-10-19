---
type: entity
title: "engines/eval/speaker_sim.py"
entity_type: module
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "engines/eval/speaker_sim.py"
language: py
depends_on: []
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

# engines/eval/speaker_sim.py

## Overview

Standalone evaluation script printing speaker-embedding cosine similarity (WeSpeaker ResNet34-LM ONNX) between a reference WAV and others; intended to run from the Chatterbox venv (`engines/eval/speaker_sim.py:1-6`).

## Signature / Definition

```python
def read(path, sr=16000) -> np.ndarray
def fbank(x, sr=16000, n_mels=80) -> np.ndarray
def embed(sess, path) -> np.ndarray
def main(argv)
```

## Behavior

- Model path `engines/eval/models/voxceleb_resnet34_LM.onnx` (`speaker_sim.py:18`).
- `embed` L2-normalises the ONNX output (`:64-66`); `main` prints `ref @ embed` per file (`:69-73`).
- Imports no `naturalvoice` code (`:10-16`); no callers found in `src/`, `tests/` or `scripts/`.

## Connections

- **depends_on:** none in chunk
- **used_by:** none found
- **related concepts:** [[concepts/cleanup-processing-pipeline]], [[concepts/cleanup-job-lifecycle]]

## Tested by

- none found

## History

- **Scan HEAD:** commit `0a207b3` (`dev`), 2026-10-18. Per-symbol git history not traced in this partial scan.

## Sources

- `engines/eval/speaker_sim.py` (lines 1-77)
