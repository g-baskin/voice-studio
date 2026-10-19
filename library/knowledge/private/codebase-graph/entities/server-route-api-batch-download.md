---
type: entity
title: "POST /api/batch-download"
entity_type: function
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/server.py"
language: py
depends_on:
  - "[[entities/server-route-api-jobs]]"
used_by:
  - "[[entities/web-workflow-module]]"
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

# POST /api/batch-download

## Overview

Zips the outputs of up to 20 completed full-file Clean jobs (`src/naturalvoice/server.py:176-203`).

## Signature / Definition

```python
class BatchDownload(BaseModel): jobs: list[str] = Field(min_length=1, max_length=20)
@app.post('/api/batch-download') def batch_download(request: BatchDownload)
```

## Behavior

- Dedups ids, requires 32-hex ids with status done and mode clean, else 400 (`server.py:183-187`).
- Stored (uncompressed) zip with sanitised `NN-<stem>.natural<ext>` names; temp zip deleted after send via `BackgroundTask` (`:188-203`).
- Test `test_zip_completed_only_safe_unique_names` (`tests/test_workflow.py:116`).

## Connections

- **depends_on:** [[entities/server-route-api-jobs]]
- **used_by:** [[entities/web-workflow-module]]
- **related concepts:** [[concepts/cleanup-processing-pipeline]], [[concepts/cleanup-job-lifecycle]]

## Tested by

- `tests/test_workflow.py`

## History

- **Scan HEAD:** commit `0a207b3` (`dev`), 2026-10-18. Per-symbol git history not traced in this partial scan.

## Sources

- `src/naturalvoice/server.py` (lines 176-203)
