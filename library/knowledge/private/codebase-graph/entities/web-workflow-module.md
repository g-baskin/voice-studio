---
type: entity
title: "web/workflow.js (Clean page client)"
entity_type: module
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/web/workflow.js"
language: js
depends_on:
  - "[[entities/server-route-api-clean]]"
  - "[[entities/server-route-api-jobs]]"
  - "[[entities/server-route-api-batch-download]]"
used_by:
  - "[[entities/web-index-html]]"
tested_by: []
last_commit_hash: "0a207b37dc9809791194e8b796c9113351ebfb6e"
tags:
  - entity
  - cleanup
related:
  - "[[concepts/cleanup-processing-pipeline]]"
sources: []
---

# web/workflow.js (Clean page client)

## Overview

Browser client for the Clean workspace: file queue, preview sections, job submission, polling and batch download (`src/naturalvoice/web/workflow.js`). Read as source; not parsed by an AST tool.

## Signature / Definition

```js
function renderQueue(), pickMany(files), section(), runJob(item, mode, settings, bounds),
runSelected(mode), chooseTrack(index), showResult(job, result, name, templateLabel)
```

## Behavior

- `runJob` posts FormData (file, mode, preset, controls, start, seconds) to `api/clean`, then polls `api/jobs/<id>` sequentially every 700 ms (`workflow.js:170-190`).
- Batch download posts JSON `{jobs}` to `api/batch-download` (`:292-300`).
- Loaded by `index.html` (`src/naturalvoice/web/index.html:351`).

## Connections

- **depends_on:** [[entities/server-route-api-clean]], [[entities/server-route-api-jobs]], [[entities/server-route-api-batch-download]]
- **used_by:** [[entities/web-index-html]]
- **related concepts:** [[concepts/cleanup-processing-pipeline]], [[concepts/cleanup-job-lifecycle]]

## Tested by

- none found

## History

- **Scan HEAD:** commit `0a207b3` (`dev`), 2026-10-18. Per-symbol git history not traced in this partial scan.

## Sources

- `src/naturalvoice/web/workflow.js` (lines 12-466)
- `src/naturalvoice/web/index.html` (line 351)
