---
type: entity
title: "server.app (FastAPI shell)"
entity_type: service
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/server.py"
language: py
depends_on:
  - "[[entities/humanize-settings]]"
  - "[[entities/audio-module]]"
  - "[[entities/voices-module]]"
  - "[[entities/voicelab_api-module]]"
  - "[[entities/studio-api-module]]"
  - "[[entities/clone_api-module]]"
  - "[[entities/sample_library_api-module]]"
  - "[[entities/sample_library_api-module]]"
  - "[[entities/rewrite-module]]"
  - "[[entities/scriptgen-module]]"
  - "[[entities/llm-api-module]]"
used_by:
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

# server.app (FastAPI shell)

## Overview

FastAPI application titled "Voice Studio" that serves the Clean routes, mounts feature routers and the static web shell (`src/naturalvoice/server.py:23-31`, `:228-245`).

## Signature / Definition

```python
app = FastAPI(title='Voice Studio')
jobs: dict[str, dict] = {}
processing = threading.BoundedSemaphore(1)
WORK = Path(tempfile.gettempdir()) / 'naturalvoice'
MAX_BYTES = 500 * 1024 * 1024
```

## Behavior

- In-memory `jobs` dict and a single-slot semaphore bound processing to one job (`server.py:29-31`).
- Routes in this file: `GET /api/presets` (`:41-43`), `GET /api/voices` returning ids plus catalog, 503 on `RuntimeError` (`:46-55`), [[entities/server-route-api-clean]], [[entities/server-route-api-jobs]], [[entities/server-route-api-batch-download]], [[entities/server-route-api-speak]].
- Adds `sample_library_api.SampleUploadLimit` middleware and includes seven feature routers before the static mount (`:230-243`).
- Mounts `web/` at `/` with `html=True` last, because it catches everything (`:229`, `:245`); see [[entities/web-workflow-module]], [[entities/web-sw-module]].

## Connections

- **depends_on:** [[entities/humanize-settings]], [[entities/audio-module]], [[entities/voices-module]], [[entities/voicelab_api-module]], [[entities/studio-api-module]], [[entities/clone_api-module]], [[entities/sample_library_api-module]], [[entities/sample_library_api-module]], [[entities/rewrite-module]], [[entities/scriptgen-module]], [[entities/llm-api-module]]
- **used_by:** [[entities/cli-main]]
- **related concepts:** [[concepts/cleanup-processing-pipeline]], [[concepts/cleanup-job-lifecycle]]

## Tested by

- `tests/test_workflow.py`

## History

- **Scan HEAD:** commit `0a207b3` (`dev`), 2026-10-18. Per-symbol git history not traced in this partial scan.

## Sources

- `src/naturalvoice/server.py` (lines 1-245)
