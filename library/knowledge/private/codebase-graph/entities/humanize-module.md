---
type: entity
title: "humanize module"
entity_type: module
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/humanize.py"
language: py
depends_on:
  - "[[entities/enhance-ai-clean]]"
used_by:
  - "[[entities/workflow-process]]"
  - "[[entities/tts-speak]]"
  - "[[entities/cli-main]]"
  - "[[entities/server-app]]"
  - "[[entities/analyze-report]]"
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

# humanize module

## Overview

The Clean workspace's DSP cleanup chain (`src/naturalvoice/humanize.py:1-14`). The module docstring maps each synthetic-speech artifact to a stage: dereverberation, resonance notching (de-metal), dynamic de-harsh, warmth, spectral denoise, optional room tone and loudness normalisation to -16 LUFS.

## Signature / Definition

```python
Settings, PRESETS, get_settings, estimate_rt60, dereverb, find_resonances,
demetal, deharsh, tone, denoise, add_room_tone, soft_limit, normalize,
process_mono, humanize
```

## Behavior

- Exports [[entities/humanize-settings]] and the cleanup presets (`humanize.py:25-58`).
- Stage functions: `estimate_rt60` (`:87-119`), `dereverb` (`:122-163`), `find_resonances` (`:166-191`), `demetal` (`:194-215`), `deharsh` (`:218-241`), `tone` via pedalboard filters (`:244-261`), `denoise` via `nr.reduce_noise` (`:264-270`), `add_room_tone` seeded at 7 (`:273-283`), `soft_limit` (`:286-307`), `normalize` with pyloudnorm meter and `soft_limit` (`:310-326`).
- Orchestrators: [[entities/humanize-humanize]] (`:332-368`).
- Imports only numpy and scipy at module level (`:18-22`); `enhance` is imported lazily inside `process_mono` (`:333`).
- `analyze` reuses its private `_stft` and `find_resonances` (`src/naturalvoice/analyze.py:13`).

## Connections

- **depends_on:** [[entities/enhance-ai-clean]]
- **used_by:** [[entities/workflow-process]], [[entities/tts-speak]], [[entities/cli-main]], [[entities/server-app]], [[entities/analyze-report]], [[entities/bench-run]]
- **related concepts:** [[concepts/cleanup-processing-pipeline]], [[concepts/cleanup-job-lifecycle]]

## Tested by

- `tests/test_core.py`

## History

- **Scan HEAD:** commit `0a207b3` (`dev`), 2026-10-18. Per-symbol git history not traced in this partial scan.

## Sources

- `src/naturalvoice/humanize.py` (lines 1-368)
- `src/naturalvoice/analyze.py` (line 13)
