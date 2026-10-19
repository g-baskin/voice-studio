---
type: entity
title: "web/index.html (Clean page shell)"
entity_type: module
status: seed
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/web/index.html"
language: unknown
source_extension: ".html"
depends_on:
  - "[[entities/web-workflow-module]]"
used_by:
  - "[[entities/server-app]]"
last_commit_hash: "0a207b37dc9809791194e8b796c9113351ebfb6e"
tested_by: []
tags:
  - entity
  - cleanup
related:
  - "[[concepts/cleanup-processing-pipeline]]"
sources: []
---

# web/index.html (Clean page shell)

## Overview

Static HTML page titled "Voice Studio" (`src/naturalvoice/web/index.html:7`) served from the `web` directory by the server's static mount (`src/naturalvoice/server.py:23`, `server.py:245`). It hosts the "Fix a voice" and "Text to voice" tabs (`index.html:78-80`).

## Behavior

- Links the web manifest, icons and `app.css` (`index.html:8-12`).
- Inline script (`index.html:189` onward) defines cleanup slider labels and templates, and fetches `api/presets` (`:286`), `api/voices` (`:306`) and posts to `api/speak` (`:340`).
- Loads `workflow.js` last (`index.html:351`).

## Connections

- **depends_on:** [[entities/web-workflow-module]] (`index.html:351`), [[entities/server-route-api-speak]] (`index.html:340`)
- **used_by:** [[entities/server-app]] (`server.py:245`)
- **related concepts:** [[concepts/cleanup-processing-pipeline]]

## Sources

- `src/naturalvoice/web/index.html` (lines 7-12, 78-80, 189, 286, 306, 340, 351)
- `src/naturalvoice/server.py` (lines 23, 245)
