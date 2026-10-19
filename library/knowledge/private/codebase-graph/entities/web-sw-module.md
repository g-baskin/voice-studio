---
type: entity
title: "web/sw.js (service worker)"
entity_type: module
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/web/sw.js"
language: js
depends_on: []
used_by: []
tested_by: []
last_commit_hash: "0a207b37dc9809791194e8b796c9113351ebfb6e"
tags:
  - entity
  - cleanup
related:
  - "[[concepts/cleanup-processing-pipeline]]"
sources: []
---

# web/sw.js (service worker)

## Overview

Minimal service worker caching the app shell so the page installs as an app (`src/naturalvoice/web/sw.js:1`).

## Signature / Definition

```js
const CACHE = 'naturalvoice-v4'
const SHELL = ['./', 'index.html', 'workflow.js', 'app.css', ...]
```

## Behavior

- Install caches `SHELL` (`sw.js:2-18`); activate deletes older `naturalvoice-*` caches (`:19-29`).
- Fetch: never intercepts non-GET or `/api/` requests; otherwise network first, cache fallback (`:30-37`).
- Registration site not located in this chunk (recorded as a gap).

## Connections

- **depends_on:** none in chunk
- **used_by:** none found
- **related concepts:** [[concepts/cleanup-processing-pipeline]], [[concepts/cleanup-job-lifecycle]]

## Tested by

- none found

## History

- **Scan HEAD:** commit `0a207b3` (`dev`), 2026-10-18. Per-symbol git history not traced in this partial scan.

## Sources

- `src/naturalvoice/web/sw.js` (lines 1-37)
