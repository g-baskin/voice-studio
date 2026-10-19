---
type: entity
title: "web/studio.html and studio.js (Studio front end)"
entity_type: module
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/web/studio.js"
language: js
depends_on:
  - "[[studio-api-module]]"
  - "[[llm-api-module]]"
  - "[[scriptgen-module]]"
  - "[[rewrite-module]]"
  - "[[clone-module]]"
  - "[[voices-module]]"
used_by: []
last_commit_hash: "35c85ddcc30466e8280841dbdfaf7ceb0b22fcba"
tested_by:
  - "tests/browser_studio.cjs"
tags:
  - entity
  - studio
related: []
sources:
  - "src/naturalvoice/web/studio.js"
  - "src/naturalvoice/web/studio.html"
---

# Studio front end

## Overview

Plain browser script (read as source, no parser) loaded by `studio.html` (`src/naturalvoice/web/studio.html:286`); `studio.html` last changed in `4e17b0f`. Shared stylesheet `app.css` (`src/naturalvoice/web/studio.html:12`).

## Server calls

- `api(path)` wraps `fetch('/api/studio' + path)` and turns pydantic error details into messages (`src/naturalvoice/web/studio.js:69-80`).
- Studio routes: `/preview` (`:670`, `:745`), `/projects` (`:1469`), `/music` (`:1581`), `/subtitles` (`:1617`), `/video` (`:1650`), `/renders` (`:1856`), `/presets` (`:1900`), `/styles` (`:1906`); render files via `fileUrl` (`:1778`).
- Writing assist: `/api/rewrite` (`:425`), `/api/llm/key` PUT/DELETE (`:1164`, `:1190`), `/api/scriptgen/status`, POST, `/sample` (`:1202`, `:1264`, `:1319`).
- Other chunks: `/api/clone/status` (`:1907`), `/api/voices` (`:1917`).

## Connections

- depends_on: [[studio-api-module]], [[llm-api-module]], [[scriptgen-module]], [[rewrite-module]], [[clone-module]], [[voices-module]]
- served by: [[entities/server-app]]
