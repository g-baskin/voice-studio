---
type: entity
title: "analyze.report (artifact measurements)"
entity_type: function
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/analyze.py"
language: py
depends_on:
  - "[[entities/humanize-module]]"
  - "[[entities/quality-dnsmos]]"
used_by:
  - "[[entities/workflow-process]]"
  - "[[entities/workflow-recommend]]"
  - "[[entities/cli-main]]"
  - "[[entities/cli-main]]"
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

# analyze.report (artifact measurements)

## Overview

Measures echo, metallic and harshness of a recording and an optional DNSMOS listener score (`src/naturalvoice/analyze.py:50-68`).

## Signature / Definition

```python
def echo_db(x, sr) -> float
def metallic(x, sr) -> float
def harshness_db(x, sr) -> float
def listener_score(x, sr, max_seconds=60.0) -> float | None
def report(audio, sr) -> dict
```

## Behavior

- `metallic` sums `find_resonances` output and `harshness_db` uses `_stft`, both imported from humanize (`analyze.py:13`, `:27-37`).
- `listener_score` and `report` call `quality.dnsmos` (`:40-68`).
- [[entities/workflow-process]] calls `report` before and after cleanup (`src/naturalvoice/workflow.py:148`, `:157`).

## Connections

- **depends_on:** [[entities/humanize-module]], [[entities/quality-dnsmos]]
- **used_by:** [[entities/workflow-process]], [[entities/workflow-recommend]], [[entities/cli-main]], [[entities/cli-main]]
- **related concepts:** [[concepts/cleanup-processing-pipeline]], [[concepts/cleanup-job-lifecycle]]

## Tested by

- `tests/test_workflow.py`

## History

- **Scan HEAD:** commit `0a207b3` (`dev`), 2026-10-18. Per-symbol git history not traced in this partial scan.

## Sources

- `src/naturalvoice/analyze.py` (lines 1-68)
