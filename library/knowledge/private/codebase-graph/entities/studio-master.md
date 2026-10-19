---
type: entity
title: "studio.master"
entity_type: function
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/studio.py"
language: py
depends_on:
  - "[[humanize-module]]"
used_by:
  - "[[studio-render-project]]"
last_commit_hash: "35c85ddcc30466e8280841dbdfaf7ceb0b22fcba"
tested_by:
  - "tests/test_studio.py:86"
  - "tests/test_studio.py:264"
tags:
  - entity
  - studio
related: []
sources:
  - "src/naturalvoice/studio.py"
---

# studio.master

## Overview

Brings the Mix to a delivery target from `TARGETS`; returns audio, linear pre-limiter gain and a report (`src/naturalvoice/studio.py:863-864`).

## Behavior

- `raw`: levels untouched, warns about clipping (`src/naturalvoice/studio.py:867-879`).
- `acx`: RMS gain to -20 dBFS, iterative `hz.soft_limit` until true peak <= -3 dB; checks RMS -23..-18, peak, noise floor <= -60 (`src/naturalvoice/studio.py:880-904`).
- LUFS targets (youtube -14, podcast -16, broadcast -23): up to 6 passes of gain plus soft limit, met if within 1 LU and under true peak (`src/naturalvoice/studio.py:905-930`, `:110-113`).
- Measurement helpers: `true_peak_db`, `lufs` (pyloudnorm, lazy import), `rms_db`, `noise_floor_db`, `measure` (`src/naturalvoice/studio.py:819-860`).
- ACX room tone is added deliberately by `room_tone` at -65 dBFS (`src/naturalvoice/studio.py:38`, `:807`); do not remove it as noise.

## Connections

- depends_on: [[humanize-module]]
- used_by: [[studio-render-project]] (via `_master_project_audio`)
