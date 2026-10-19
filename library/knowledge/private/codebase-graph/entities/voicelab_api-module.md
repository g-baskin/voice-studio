---
type: entity
title: "voicelab_api module (/api/voicelab routes)"
entity_type: module
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/voicelab_api.py"
language: py
depends_on:
  - "[[entities/voicelab-module]]"
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
  - "src/naturalvoice/voicelab_api.py"
---

# voicelab_api module (/api/voicelab routes)

## Overview

FastAPI router at `/api/voicelab` (`src/naturalvoice/voicelab_api.py:21`) for the Voice Lab workspace: library listing (`:68`), preview (`:110`), rename/star/delete (`:132`, `:147`, `:154`), design preview/save (`:188`, `:203`), describe (`:232`) and match jobs (`match_start` `:254`, status `:331`, cancel `:339`, audio `:346`, save `:366`).

## Limits

- Upload max 100 MB, extensions wav/mp3/m4a/mp4 (`voicelab_api.py:23-24`); match reference 10 to 60 s (`:25`); budget 5 to 600 s (`:26`).
- Match jobs live in the in-memory dict `match_jobs` (`:27`).

## Connections

- **imports:** [[entities/voicelab-module]] (`:18`), [[entities/voices-module]] (`:19`)
- **mounted by:** [[entities/server-app]] (`server.py:230`, `:235`)
- **frontend:** `src/naturalvoice/web/voicelab.js`

## History

- **Last touched:** commit `0a207b3` (feat: add local voice sample collections) by AutomationGod on 2026-10-18, per `git log`.
