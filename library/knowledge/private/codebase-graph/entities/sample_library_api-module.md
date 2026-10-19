---
type: entity
title: "sample_library_api module (/api/samples routes)"
entity_type: module
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/sample_library_api.py"
language: py
depends_on:
  - "[[entities/sample_library-module]]"
used_by:
  - "[[entities/server-app]]"
last_commit_hash: "0a207b37dc9809791194e8b796c9113351ebfb6e"
tested_by:
  - "tests/test_sample_library.py"
tags:
  - entity
  - voices
related: []
sources:
  - "src/naturalvoice/sample_library_api.py"
---

# sample_library_api module (/api/samples routes)

## Overview

FastAPI router at `/api/samples` with a router-wide `local_request` dependency (`src/naturalvoice/sample_library_api.py:83`).

## Exports

- `local_request`: requires a loopback peer, a localhost host name, same-origin `Origin`, and rejects `sec-fetch-site: cross-site` (`:23-34`). Not authentication (ADR 0004).
- `SampleUploadLimit` ASGI middleware: bounds `POST /api/samples/sources` bodies to 250 MB + 64 KB before multipart spooling (`:37-80`); added by `server.py:232`.
- `errors()` maps KeyError 404, ValueError 400, OSError 507 (`:86-95`).
- `launch` runs [[entities/sample_library-process_source]] on a thread (`:104-112`).
- Routes: catalog (`:116`), import source (`:127-205`), source/retry/audio (`:209`, `:215`, `:237`), person create/get (`:251`, `:257`), add sample (`:276`), sample audio (`:282`), build version (`:293`), activate (`:303`).

## Connections

- **imports:** [[entities/sample_library-module]] (`:20`); lazy [[entities/server-app]] `processing` semaphore (`:98-101`)
- **mounted by:** [[entities/server-app]] (`server.py:238`)
- **frontend:** `src/naturalvoice/web/samples.js`, `samples.html`
- **tested by:** `tests/test_sample_library.py:76-84` (browser boundary, same origin, remote peer), `:140` (upload rejected before spooling)

## History

- **Last touched:** commit `0a207b3` (feat: add local voice sample collections) by AutomationGod on 2026-10-18, per `git log`.
