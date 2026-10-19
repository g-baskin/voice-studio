---
type: entity
title: "sample_library.build_version"
entity_type: function
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/sample_library.py"
language: py
depends_on:
  - "[[entities/voices-save_clone]]"
  - "[[entities/sample_library-module]]"
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

# sample_library.build_version

## Overview

Builds a new **cloned voice** reference version for a person from selected samples (`src/naturalvoice/sample_library.py:334-372`). It concatenates recordings; it does not train any model (`method: "reference-selection-not-training"`, `:370`).

## Signature / Definition

```py
def build_version(person: str, sample_ids: list[str]) -> dict
```

## Behavior

- 1 to 40 distinct samples, all owned by the person, totalling 5 to 20 s (`:335-344`), matching the Chatterbox conditioning limit (ADR 0004).
- Holds the `writing()` lock throughout (`:337`), checks quota (`:345`).
- Resamples each sample to 24 kHz with 192-sample fades (`:347-353`).
- Sequence = max existing `reference_version` + 1 (`:355`); saves via [[entities/voices-save_clone]] with provenance meta (`:359-371`). Prior versions are untouched.

## Connections

- **depends_on:** [[entities/voices-save_clone]]
- **used_by:** `build` route in [[entities/sample_library_api-module]] (`sample_library_api.py:293-295`)
- **tested by:** `tests/test_sample_library.py:181` (versions and rollback), `:299` (concurrent version numbers), `:206` (length boundaries)
- **concepts:** [[concepts/voices-reference-versioning]]

## History

- **Last touched:** commit `0a207b3` (feat: add local voice sample collections) by AutomationGod on 2026-10-18, per `git log`.
