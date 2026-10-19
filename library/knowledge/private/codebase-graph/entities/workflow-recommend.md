---
type: entity
title: "workflow.recommend (cleanup suggestion)"
entity_type: function
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/workflow.py"
language: py
depends_on:
  - "[[entities/analyze-report]]"
  - "[[entities/humanize-module]]"
used_by:
  - "[[entities/workflow-process]]"
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

# workflow.recommend (cleanup suggestion)

## Overview

Computes a suggested cleanup template from measured echo, metallic tone and RT60 for `analyze` mode (`src/naturalvoice/workflow.py:47-81`).

## Signature / Definition

```python
def recommend(data: np.ndarray, sr: int) -> dict
```

## Behavior

- Uses `analyze.echo_db`, `analyze.metallic`, `hz._stft` and `hz.estimate_rt60` (per ast call list for `workflow.py:47-81`).
- Called only from the `analyze` branch of [[entities/workflow-process]] (`workflow.py:146`).
- Test name `test_suggestion_is_advisory_and_has_no_output` (`tests/test_workflow.py:77`).

## Connections

- **depends_on:** [[entities/analyze-report]], [[entities/humanize-module]]
- **used_by:** [[entities/workflow-process]]
- **related concepts:** [[concepts/cleanup-processing-pipeline]], [[concepts/cleanup-job-lifecycle]]

## Tested by

- `tests/test_workflow.py`

## History

- **Scan HEAD:** commit `0a207b3` (`dev`), 2026-10-18. Per-symbol git history not traced in this partial scan.

## Sources

- `src/naturalvoice/workflow.py` (lines 47-81)
