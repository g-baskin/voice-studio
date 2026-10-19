---
type: entity
title: "voicelab.match (voice matching)"
entity_type: function
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/voicelab.py"
language: py
depends_on:
  - "[[entities/voicelab-stock_features]]"
used_by:
  - "[[entities/voicelab_api-module]]"
last_commit_hash: "0a207b37dc9809791194e8b796c9113351ebfb6e"
tested_by: []
tags:
  - entity
  - voices
related: []
sources:
  - "src/naturalvoice/voicelab.py"
---

# voicelab.match (voice matching)

## Overview

**Voice matching**: searches Kokoro voice-vector space for a vector whose rendering resembles a recording, scored by cosine similarity of CAM++ speaker embeddings (`src/naturalvoice/voicelab.py:590-600`). It is not cloning: the output is a vector within stock-voice space.

## Signature / Definition

```py
def match(ref: np.ndarray, ref_sr: int, budget_s: float = 180, candidates: list[str] | None = None, top_k: int = 3, progress=None, cancel=None, seed: int = 0) -> dict
```

## Behavior

- Time-budgeted refinement with shrinking sigma (`voicelab.py:640-641`), progress reported per try (`:642-647`).
- Returns `style`, `start_style`, `before`/`after` similarity, `best_stock`, `tries`, `kept`, `seconds` (`voicelab.py:648-657`).
- Runs as a background job started by `match_start` (`voicelab_api.py:254-320`); result saved as a custom voice by `match_save` (`voicelab_api.py:366-385`).

## Connections

- **depends_on:** [[entities/voicelab-stock_features]]
- **concepts:** [[concepts/voices-voice-categories]]

## History

- **Last touched:** commit `0a207b3` (feat: add local voice sample collections) by AutomationGod on 2026-10-18, per `git log`.
