---
type: entity
title: "GET /api/jobs/{job} and /api/jobs/{job}/{which}"
entity_type: function
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/server.py"
language: py
depends_on:
  - "[[entities/server-route-api-clean]]"
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

# GET /api/jobs/{job} and /api/jobs/{job}/{which}

## Overview

Job status polling and per-job file download for Clean jobs (`src/naturalvoice/server.py:144-173`).

## Signature / Definition

```python
@app.get('/api/jobs/{job}')        def job_status(job)
@app.get('/api/jobs/{job}/{which}') def job_file(job, which)
```

## Behavior

- Status omits the internal `output` path; 404 for unknown job (`server.py:145-149`).
- `which`: `compare-before`/`compare-after` once done and not analyze (`:158-159`); `original` (`:160-164`); `result` named `<stem>.preview` or `<stem>.natural` (`:165-172`); else 404 (`:173`).
- Polled every 700 ms by `runJob` (`src/naturalvoice/web/workflow.js:182-189`).

## Connections

- **depends_on:** [[entities/server-route-api-clean]]
- **used_by:** [[entities/web-workflow-module]]
- **related concepts:** [[concepts/cleanup-processing-pipeline]], [[concepts/cleanup-job-lifecycle]]

## Tested by

- `tests/test_workflow.py`

## History

- **Scan HEAD:** commit `0a207b3` (`dev`), 2026-10-18. Per-symbol git history not traced in this partial scan.

## Sources

- `src/naturalvoice/server.py` (lines 144-173)
- `src/naturalvoice/web/workflow.js` (lines 170-190)
