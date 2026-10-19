---
type: entity
title: "chatterbox worker main (JSON-lines loop)"
entity_type: function
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "engines/chatterbox/worker.py"
language: py
depends_on: []
used_by:
  - "[[entities/clone-_Worker]]"
last_commit_hash: "0a207b37dc9809791194e8b796c9113351ebfb6e"
tested_by: []
tags:
  - entity
  - voices
related: []
sources:
  - "engines/chatterbox/worker.py"
---

# chatterbox worker main (JSON-lines loop)

## Overview

Entry point of the isolated cloning engine, run in its own Python environment (`engines/chatterbox/worker.py:126-166`). Protocol documented in the module docstring (`worker.py:1-8`).

## Signature / Definition

```py
def main()  # reads JSON lines on stdin, writes JSON lines on stdout
```

## Behavior

- Redirects `sys.stdout` to stderr so library prints cannot corrupt the protocol (`worker.py:127-128`).
- Loads `Engine` once (four ONNX sessions plus tokenizer, `worker.py:44-60`); writes `{"id": 0, "ok": true, "ready": true}` or a load error and exits (`:129-136`).
- Ops: `ping`, `speak` (text + ref -> `.npy`), `convert` (src + ref -> `.npy`); unknown op -> `ok: false` (`:144-157`). Errors are returned per request, loop continues (`:158-162`).
- Reference must be 24 kHz mono 16-bit WAV (`worker.py:65-67`); conditioning cached for one reference keyed by path and mtime (`:62-71`).

## Connections

- **called by:** [[entities/clone-_Worker]] (`clone.py:136-146`, `:182`)
- **concepts:** [[concepts/voices-isolated-engines]]
- **ADR:** `docs/adr/0001-isolate-the-cloning-engine.md`

## History

- **Last touched:** commit `0a207b3` (feat: add local voice sample collections) by AutomationGod on 2026-10-18, per `git log`.
