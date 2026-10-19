---
type: entity
title: "voices.save_clone"
entity_type: function
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/voices.py"
language: py
depends_on:
  - "[[entities/voices-module]]"
used_by:
  - "[[entities/sample_library-build_version]]"
  - "[[entities/clone_api-module]]"
last_commit_hash: "0a207b37dc9809791194e8b796c9113351ebfb6e"
tested_by: []
tags:
  - entity
  - voices
related: []
sources:
  - "src/naturalvoice/voices.py"
---

# voices.save_clone

## Overview

Registers a **cloned voice**: moves a reference recording into the library under id `clone:<vid>` (`src/naturalvoice/voices.py:92-110`). No vector is stored.

## Signature / Definition

```py
def save_clone(name: str, wav_bytes_path: Path, meta: dict | None = None, lang: str = "en-us") -> dict
```

## Behavior

- Moves (not copies) the WAV via `Path.replace` (`voices.py:100`).
- Record carries `kind: "clone"` and caller `meta` (`voices.py:101-108`). Sample collections put provenance (`sample_person`, `reference_version`) in `meta` (`sample_library.py:362-371`).
- Each call creates a new id; it never overwrites an existing clone, which is what makes [[concepts/voices-reference-versioning]] safe.

## Connections

- **used_by:** [[entities/sample_library-build_version]] (`sample_library.py:359`), [[entities/clone_api-module]] create route (`clone_api.py:94`)
- **concepts:** [[concepts/voices-voice-categories]], [[concepts/voices-reference-versioning]]

## History

- **Last touched:** commit `0a207b3` (feat: add local voice sample collections) by AutomationGod on 2026-10-18, per `git log`.
