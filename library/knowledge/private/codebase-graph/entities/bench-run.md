---
type: entity
title: "bench.run (cleanup benchmark)"
entity_type: function
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/bench.py"
language: py
depends_on:
  - "[[entities/audio-module]]"
  - "[[entities/analyze-report]]"
  - "[[entities/humanize-humanize]]"
  - "[[entities/quality-dnsmos]]"
  - "[[entities/tts-speak]]"
  - "[[entities/enhance-ai-clean]]"
used_by:
  - "[[entities/cli-main]]"
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

# bench.run (cleanup benchmark)

## Overview

Benchmarks cleanup methods against synthetic damage on TTS reference sentences and writes `results.json` and `REPORT.md` (`src/naturalvoice/bench.py:218-241`).

## Signature / Definition

```python
DAMAGE: dict[str, Callable]
def methods() -> dict[str, Callable]
def score(ref, y, sr, full=True) -> dict
def references(out_dir, voices=3) -> list
def run(out_dir='bench', quick=False, save_audio=True, log=print) -> dict
def summarize(rows, method_names) -> dict
def render(r) -> str
```

## Behavior

- Damage generators: room simulation, synthetic reverb, Griffin-Lim, resonances, codec round trip (`bench.py:55-143`).
- `methods()` compares untouched, AI cleanup, presets via `hz.get_settings`/`hz.humanize` (`:145-158`).
- `score` combines DNSMOS, PESQ, STOI, echo and metallic (`:170-193`); `references` renders refs with `tts.speak` (`:203-215`).
- Exercised in `tests/test_core.py:86-155`.

## Connections

- **depends_on:** [[entities/audio-module]], [[entities/analyze-report]], [[entities/humanize-humanize]], [[entities/quality-dnsmos]], [[entities/tts-speak]], [[entities/enhance-ai-clean]]
- **used_by:** [[entities/cli-main]]
- **related concepts:** [[concepts/cleanup-processing-pipeline]], [[concepts/cleanup-job-lifecycle]]

## Tested by

- `tests/test_core.py`

## History

- **Scan HEAD:** commit `0a207b3` (`dev`), 2026-10-18. Per-symbol git history not traced in this partial scan.

## Sources

- `src/naturalvoice/bench.py` (lines 22-309)
- `tests/test_core.py` (lines 10, 86-155)
