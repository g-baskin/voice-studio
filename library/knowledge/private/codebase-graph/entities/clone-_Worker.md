---
type: entity
title: "clone._Worker (persistent engine client)"
entity_type: class
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/clone.py"
language: py
depends_on:
  - "[[entities/chatterbox_worker-main]]"
used_by:
  - "[[entities/clone-module]]"
last_commit_hash: "0a207b37dc9809791194e8b796c9113351ebfb6e"
tested_by: []
tags:
  - entity
  - voices
related: []
sources:
  - "src/naturalvoice/clone.py"
---

# clone._Worker (persistent engine client)

## Overview

Singleton (`_worker`, `src/naturalvoice/clone.py:200`) that owns the persistent Chatterbox subprocess and its JSON-lines protocol (`clone.py:97-197`).

## Public methods

- `call(req, timeout)`: under a lock, starts the process if not running, assigns an incrementing `id`, writes one JSON line, waits for the matching id, re-arms the idle timer (`clone.py:173-189`). Raises `RuntimeError` on `ok: false` (`:187-188`).
- `running` property (`:191-193`); `stop()` (`:195-197`).

## Lifecycle

- `_start`: raises `EngineMissing` if not installed (`:133-134`); `Popen` of `engines/chatterbox/.venv/bin/python worker.py`, stdin/stdout pipes, stderr discarded, `cwd` engine dir (`:136-144`); a daemon reader thread queues stdout lines (`:106-109`, `:145`); waits for the id-0 ready message up to `LOAD_TIMEOUT = 300` s (`:146`, `:29`).
- `_wait`: kills the process on timeout or EOF (`:115-121`); ignores non-JSON lines (`:122-125`).
- Idle shutdown after `NATURALVOICE_CLONE_IDLE` (default 600 s) (`:28`, `:161-171`).
- `_kill` closes stdin, waits 5 s, then kills (`:151-159`).

## Connections

- **peer across process boundary:** [[entities/chatterbox_worker-main]]
- **concepts:** [[concepts/voices-isolated-engines]]

## History

- **Last touched:** commit `0a207b3` (feat: add local voice sample collections) by AutomationGod on 2026-10-18, per `git log`.
