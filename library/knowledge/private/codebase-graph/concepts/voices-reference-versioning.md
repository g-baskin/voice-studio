---
type: concept
title: "Reference versioning for cloned voices"
complexity: intermediate
domain: voices
aliases: []
created: 2026-10-19
updated: 2026-10-19
status: developing
tags:
  - concept
  - voices
related:
  - "[[entities/sample_library-build_version]]"
  - "[[entities/voices-save_clone]]"
sources: []
---

# Reference versioning for cloned voices

## Definition

Adding recordings to a person's sample collection never edits an existing cloned voice. Each build creates a new `clone:` voice with `reference_version` N+1 and sample provenance ([[entities/sample_library-build_version]], `src/naturalvoice/sample_library.py:355-371`). Decision: `docs/adr/0004-isolate-media-analysis-and-version-references.md`.

## How it works

1. Sources and samples are immutable records published with `atomic_json` after audio is written (`sample_library.py:53-63`, `:310`, `:325`).
2. Mutations serialize on a filesystem `flock` across threads and server processes (`sample_library.py:80-89`).
3. `versions(person)` filters library clones by `meta.sample_person` (`:329-331`).
4. `activate` records a preferred version on the person; it does not rewrite Studio projects or delete older WAVs (`:375-382`).
5. Reference length 5 to 20 s matches the Chatterbox conditioning limit (`:343-344`; `clone.py:30`).

## Why it matters

Quality can regress with new samples; older references and project voice ids stay valid. This is reference selection, not training (`sample_library.py:370`).

## Examples / tests

- `tests/test_sample_library.py:181` (versions and rollback), `:284` (atomic publication preserves previous), `:299` (concurrent version numbers)

## Connections

- [[entities/voices-save_clone]], [[concepts/voices-voice-categories]], [[concepts/voices-isolated-engines]]
