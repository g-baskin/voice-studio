---
type: entity
title: "cli.main (voicestudio CLI)"
entity_type: function
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/cli.py"
language: py
depends_on:
  - "[[entities/cli-main]]"
  - "[[entities/studio-cli-render]]"
  - "[[entities/tts-speak]]"
  - "[[entities/analyze-report]]"
  - "[[entities/voices-module]]"
  - "[[entities/bench-run]]"
  - "[[entities/server-app]]"
  - "[[entities/humanize-settings]]"
used_by: []
tested_by: []
last_commit_hash: "0a207b37dc9809791194e8b796c9113351ebfb6e"
tags:
  - entity
  - cleanup
related:
  - "[[concepts/cleanup-processing-pipeline]]"
sources: []
---

# cli.main (voicestudio CLI)

## Overview

argparse entry point registered as both `voicestudio` and `naturalvoice` console scripts (`pyproject.toml:29-31`, `src/naturalvoice/cli.py:48-157`).

## Signature / Definition

```python
def main(argv=None) -> int
def clean_file(src, dst, settings, progress=None) -> dict
```

## Behavior

- Subcommands: clean, speak, analyze, voices, bench, serve, render, dub (`cli.py:54-93`).
- `render`/`dub` delegate to `studio.cli_render`, returning 2 on errors (`:104-113`).
- `clean` calls `clean_file`, which loads, reports, runs `humanize` and saves or remuxes (`:34-45`, `:115-121`).
- `speak` reads `@file` text and calls `tts.speak` (`:122-128`); `voices` lists `vlib.catalog()` (`:134-142`); `bench` runs `bench.run` and `bench.render` (`:143-147`).
- `serve` runs uvicorn on `naturalvoice.server:app`, optionally opening a browser after 1.5 s (`:148-156`).

## Connections

- **depends_on:** [[entities/cli-main]], [[entities/studio-cli-render]], [[entities/tts-speak]], [[entities/analyze-report]], [[entities/voices-module]], [[entities/bench-run]], [[entities/server-app]], [[entities/humanize-settings]]
- **used_by:** none found
- **related concepts:** [[concepts/cleanup-processing-pipeline]], [[concepts/cleanup-job-lifecycle]]

## Tested by

- none found

## History

- **Scan HEAD:** commit `0a207b3` (`dev`), 2026-10-18. Per-symbol git history not traced in this partial scan.

## Sources

- `src/naturalvoice/cli.py` (lines 1-161)
- `pyproject.toml` (lines 29-31)
