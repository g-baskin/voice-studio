---
type: concept
title: "Cleanup job lifecycle"
complexity: intermediate
domain: clean
aliases: [clean job]
created: 2026-10-19
updated: 2026-10-19
status: developing
tags:
  - concept
  - cleanup
related:
  - "[[entities/server-route-api-clean]]"
  - "[[entities/server-route-api-jobs]]"
  - "[[entities/server-route-api-batch-download]]"
  - "[[entities/web-workflow-module]]"
sources: []
---

# Cleanup job lifecycle

## Definition

How one Clean upload becomes a polled background job with downloadable outputs, across [[entities/web-workflow-module]], [[entities/server-app]] and [[entities/workflow-process]].

## How it works

1. The browser posts FormData to `api/clean` (`src/naturalvoice/web/workflow.js:170-180`).
2. The server validates the request, acquires the single-slot semaphore (429 if busy), streams the file to `WORK/<job>/input<ext>` and starts a daemon thread (`src/naturalvoice/server.py:86-140`).
3. The thread runs `workflow.process` and writes `step`/`progress` into the in-memory `jobs` dict (`server.py:121-126`).
4. The browser polls `api/jobs/<id>` every 700 ms until the job finishes or fails (`workflow.js:182-189`).
5. Outputs are `result`, `original` and `compare-before/after` (`server.py:152-173`). Full-file jobs can be zipped together (`server.py:180-203`).

## Why it matters

Job state lives in process memory only (`server.py:29`), so a server restart forgets jobs. Only one job runs at a time, and the browser batch queue is sequential by design (`server.py:30-31`). Error text is sanitised before it is exposed (`server.py:127-136`).

## Connections

- **involves entities:** [[entities/server-route-api-clean]], [[entities/server-route-api-jobs]], [[entities/server-route-api-batch-download]], [[entities/workflow-recommend]]
- **related concepts:** [[concepts/cleanup-processing-pipeline]]

## Sources

- `src/naturalvoice/server.py` (lines 23-203)
- `src/naturalvoice/web/workflow.js` (lines 170-190, 292-300)
