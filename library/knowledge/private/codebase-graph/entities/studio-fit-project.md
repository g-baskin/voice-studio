---
type: entity
title: "studio.fit_project / fit_line / timed_slot"
entity_type: function
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/studio.py"
language: py
depends_on:
  - "[[studio-render-line]]"
used_by:
  - "[[studio-render-project]]"
last_commit_hash: "35c85ddcc30466e8280841dbdfaf7ceb0b22fcba"
tested_by:
  - "tests/test_studio.py:235"
tags:
  - entity
  - studio
related: []
sources:
  - "src/naturalvoice/studio.py"
---

# studio.fit_project, fit_line, timed_slot

## Overview

Time-fitting helpers. `fit_project` fits the whole Mix to a target: speed (safe range), then fine stretch, then inter-line pauses (`src/naturalvoice/studio.py:1558-1559`). `fit_line` fits one Line to a length (`src/naturalvoice/studio.py:777-780`). `timed_slot` returns seconds available to a timed Line (`src/naturalvoice/studio.py:1471-1472`).

## Behavior

- Speed is clipped to `SAFE_SPEED` (0.85 to 1.2) and lines are re-rendered at the new speed (`src/naturalvoice/studio.py:1570`, `:1576-1583`).
- Fine stretch is clipped to `STRETCH_FINE` (`src/naturalvoice/studio.py:1587-1593`).
- Pauses move within 0.1 s to 3 s (or their own value if larger), iterated up to 20 times (`src/naturalvoice/studio.py:1594-1608`).
- Lines with their own `target` are locked (`src/naturalvoice/studio.py:1561`).
- Returns a report with `speed_factor`, `stretch`, `pause_change`, `warnings` (`src/naturalvoice/studio.py:1611-1625`).
- `timed_slot` uses the cue end or the next cue start, minimum 0.3 s (`src/naturalvoice/studio.py:1484-1489`).

## Connections

- depends_on: [[studio-render-line]]
- used_by: [[studio-render-project]]
- concepts: [[studio-render-pipeline]]
