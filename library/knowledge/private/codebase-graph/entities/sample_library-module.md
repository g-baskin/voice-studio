---
type: entity
title: "sample_library module (voice sample collections)"
entity_type: module
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/sample_library.py"
language: py
depends_on:
  - "[[entities/voices-module]]"
  - "[[entities/media_worker-analyze]]"
used_by:
  - "[[entities/sample_library_api-module]]"
last_commit_hash: "0a207b37dc9809791194e8b796c9113351ebfb6e"
tested_by:
  - "tests/test_sample_library.py"
tags:
  - entity
  - voices
related: []
sources:
  - "src/naturalvoice/sample_library.py"
---

# sample_library module (voice sample collections)

## Overview

Stores imported sources, persons and reviewed samples under `NATURALVOICE_DATA/sample-library` (`src/naturalvoice/sample_library.py:37-38`, `:47-50`) and produces new cloned-voice reference versions. Implements ADR 0004.

## Exports

- Storage: `identifier` (`:41`), `location` (`:47`), `atomic_json` (`:53-63`, temp file + fsync + `os.replace`), `read`/`records` (`:66`, `:73`), `writing()` cross-process `fcntl` lock (`:80-89`), `capacity` 2 GB quota and 1 GB free-disk floor (`:92-100`)
- Engine: `installed` (`:103-107`), `youtube_url` canonical-video allowlist (`:110-131`), `validate_window` 5 to 120 s (`:134-138`), `decode` via ffmpeg with protocol/format whitelists (`:141-176`), `download` (`:179-217`), [[entities/sample_library-process_source]] (`:220`)
- Collections: `create_person` with consent (`:267-278`), `add_sample` (`:281-326`), `versions` (`:329-331`), [[entities/sample_library-build_version]] (`:334`), `activate` (`:375-382`)

## Connections

- **imports:** [[entities/voices-module]] (`:28`)
- **subprocesses:** [[entities/media_worker-analyze]] and `engines/media/download.py` (yt-dlp with `RLIMIT_FSIZE` 250 MB, `download.py:7-8`)
- **used_by:** [[entities/sample_library_api-module]] (`sample_library_api.py:20`)
- **tested by:** `tests/test_sample_library.py` (e.g. atomic publication `:284`, concurrent versions `:299`)
- **concepts:** [[concepts/voices-reference-versioning]], [[concepts/voices-isolated-engines]]

## History

- **Last touched:** commit `0a207b3` (feat: add local voice sample collections) by AutomationGod on 2026-10-18, per `git log`.
