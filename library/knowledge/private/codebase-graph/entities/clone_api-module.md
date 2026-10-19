---
type: entity
title: "clone_api module (/api/clone routes)"
entity_type: module
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/clone_api.py"
language: py
depends_on:
  - "[[entities/clone-module]]"
  - "[[entities/voices-module]]"
used_by:
  - "[[entities/server-app]]"
last_commit_hash: "0a207b37dc9809791194e8b796c9113351ebfb6e"
tested_by: []
tags:
  - entity
  - voices
related: []
sources:
  - "src/naturalvoice/clone_api.py"
---

# clone_api module (/api/clone routes)

## Overview

FastAPI router at `/api/clone` (`src/naturalvoice/clone_api.py:28`): engine `status` (`:41-44`), `create_voice` from an upload with consent (`:52-99`, uses `clone.prepare_reference` at `:85`), text `preview` jobs (`:103-129`), voice conversion `convert` (`:204-247`), job status/audio (`:259`, `:265`).

## Limits

- 50 MB uploads; wav/mp3/m4a/mp4/webm/ogg/oga/opus (`clone_api.py:31-32`); preview text 500 chars (`:33`); at most 50 in-memory jobs (`:36-37`).

## Connections

- **imports (lazy):** [[entities/clone-module]], [[entities/voices-module]] (`clone_api.py:42`, `:55`, `:133`)
- **mounted by:** [[entities/server-app]] (`server.py:230`, `:237`)
- **frontend:** `src/naturalvoice/web/clone.js`

## History

- **Last touched:** commit `0a207b3` (feat: add local voice sample collections) by AutomationGod on 2026-10-18, per `git log`.
