---
type: concept
title: "Voice categories: custom voice, cloned voice, voice matching"
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
  - "[[entities/voices-module]]"
  - "[[entities/voicelab-match]]"
  - "[[entities/clone-module]]"
sources: []
---

# Voice categories: custom voice, cloned voice, voice matching

## Definition

Voice Studio stores two kinds of **user-created voice** (CONTEXT.md). A **custom voice** is a Kokoro voice vector (`custom:` id, `.npy`), saved by [[entities/voices-save_custom]] (`src/naturalvoice/voices.py:68-89`). A **cloned voice** is a reference recording (`clone:` id, `.wav`) consumed by the Chatterbox cloning engine, saved by [[entities/voices-save_clone]] (`voices.py:92-110`).

## How it works

- Voice Lab design ([[entities/voicelab-build_style]]) and **voice matching** ([[entities/voicelab-match]]) both yield voice vectors, so their results are custom voices.
- Cloning flows ([[entities/clone_api-module]] create route, [[entities/sample_library-build_version]]) yield cloned voices.
- `voices.resolve` hands Kokoro either a vector or a stock name (`voices.py:180-184`); `clone.speak` refuses non-`clone:` ids (`clone.py:346-347`).

## Why it matters

Calling a matched custom voice a clone misstates what it reproduces: voice matching only approximates timbre within stock-voice space. Code paths, storage files and UI wording depend on the prefix.

## Connections

- [[concepts/voices-isolated-engines]], [[concepts/voices-reference-versioning]]
