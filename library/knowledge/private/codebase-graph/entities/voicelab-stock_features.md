---
type: entity
title: "voicelab.stock_features"
entity_type: function
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/voicelab.py"
language: py
depends_on:
  - "[[entities/voicelab-module]]"
  - "[[entities/voices-module]]"
used_by:
  - "[[entities/voicelab-match]]"
last_commit_hash: "0a207b37dc9809791194e8b796c9113351ebfb6e"
tested_by: []
tags:
  - entity
  - voices
related: []
sources:
  - "src/naturalvoice/voicelab.py"
---

# voicelab.stock_features

## Overview

Returns per-stock-voice `{emb, pitch, brightness}` used by voice matching and describe (`src/naturalvoice/voicelab.py:254-280`).

## Signature / Definition

```py
def stock_features(names: list[str] | None = None, progress=None, cancel=None, cached_only: bool = False) -> dict[str, dict]
```

## Behavior

- Loads shipped `voicelab_embeddings.npz` only if its fingerprint equals `model_fingerprint()` (`voicelab.py:261-263`); the fingerprint hashes `FEATURE_VERSION`, the measure line, Kokoro voices file and speaker model (`voicelab.py:213-224`).
- Then loads the local cache `cache/stock_features_v{FEATURE_VERSION}.npz` **without** fingerprint validation and lets it override shipped entries (`voicelab.py:258`, `:266-267`).
- Renders missing voices and rewrites the local cache (`voicelab.py:270-279`), under a module lock (`:259`).

> [!note] Invariant
> Feature-semantic changes must bump `FEATURE_VERSION` so the local cache filename changes; rebuilding the shipped file alone leaves stale local results (see AGENTS.md boundaries).

## Connections

- **depends_on:** `render`, `embed`, `pitch_hz`, `brightness_hz` in [[entities/voicelab-module]]; `style_of` in [[entities/voices-module]] (`voicelab.py:273`)

## History

- **Last touched:** commit `0a207b3` (feat: add local voice sample collections) by AutomationGod on 2026-10-18, per `git log`.
