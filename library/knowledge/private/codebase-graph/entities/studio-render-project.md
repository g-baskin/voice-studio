---
type: entity
title: "studio.render_project"
entity_type: function
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/studio.py"
language: py
depends_on:
  - "[[studio-render-line]]"
  - "[[studio-fit-project]]"
  - "[[studio-master]]"
  - "[[studio-render-options]]"
used_by:
  - "[[studio-api-module]]"
  - "[[studio-cli-render]]"
last_commit_hash: "35c85ddcc30466e8280841dbdfaf7ceb0b22fcba"
tested_by:
  - "tests/test_studio.py:125"
  - "tests/test_studio.py:337"
  - "tests/test_studio.py:362"
tags:
  - entity
  - studio
related: []
sources:
  - "src/naturalvoice/studio.py"
---

# studio.render_project

## Overview

Renders a validated Project into an output directory and returns public file names (`src/naturalvoice/studio.py:1360-1363`).

## Signature

```py
def render_project(project: dict, opts: RenderOptions, out_dir: Path, progress=None, cancel: threading.Event | None = None) -> dict
```

## Behavior (stages)

1. Lint warnings and per-line rendering via `_render_project_lines` (`src/naturalvoice/studio.py:1370-1371`).
2. ACX target uses its head/tail; otherwise `lead_in` and 0.5 s tail (`src/naturalvoice/studio.py:1372-1373`).
3. Timed placement sets head to 0; otherwise optional `fit_project` to `target_duration` (`src/naturalvoice/studio.py:1376-1381`).
4. `_place_project_lines` places lines; in timed mode it keeps cue starts and records `overlap` / `overrun` entries instead of cutting (`src/naturalvoice/studio.py:1206-1252`).
5. `_mix_project_tracks` builds Stems, music and original-video beds; Mix is their sum, resampled (`src/naturalvoice/studio.py:1385-1388`).
6. Mastering via `_master_project_audio` (`src/naturalvoice/studio.py:1390`).
7. Writes mix, optional stems (same pre-limiter gain so stems sum to the mix), line clips, SRT/VTT, timeline JSON, optional dubbed video, ZIP (`src/naturalvoice/studio.py:1396-1446`).
8. Checks `cancel` between stems and raises `Cancelled` (`src/naturalvoice/studio.py:1406-1407`).

## Connections

- depends_on: [[studio-render-line]], [[studio-fit-project]], [[studio-master]], [[studio-render-options]]
- used_by: [[studio-api-module]] (`POST /api/studio/render`), [[studio-cli-render]]
- concepts: [[studio-render-pipeline]]
