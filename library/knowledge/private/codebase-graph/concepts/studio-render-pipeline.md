---
type: concept
title: "Studio render pipeline"
complexity: intermediate
domain: studio
aliases: []
created: 2026-10-19
updated: 2026-10-19
status: developing
tags:
  - concept
related:
  - "[[studio-render-project]]"
  - "[[studio-render-line]]"
  - "[[studio-fit-project]]"
  - "[[studio-master]]"
sources:
  - "src/naturalvoice/studio.py"
---

# Studio render pipeline

## Definition

How a Project becomes a Mix, Stems, captions and optional dubbed video: Line render, fit, placement, mix, master, write (`src/naturalvoice/studio.py:1360-1468`).

## How it works

1. Browser posts to `POST /api/studio/render`; the API takes the global processing lock and starts a thread ([[studio-api-module]], `src/naturalvoice/studio_api.py:419-486`).
2. Each Line renders via [[studio-render-line]], cached by content hash, with Take as seeded voice jitter.
3. Sequential placement adds pauses; Timed placement keeps cue starts and reports overlaps rather than cutting (`src/naturalvoice/studio.py:1222-1251`). Fitting is capped at 1.2x ([[studio-fit-project]]).
4. Stems per Speaker plus music bed with ducking and original-video bed form the Mix (`src/naturalvoice/studio.py:1385-1387`).
5. [[studio-master]] hits the Delivery target; ACX adds room tone deliberately.
6. Captions follow placed audio (`src/naturalvoice/studio.py:1418`); video is muxed for Dubbing (`src/naturalvoice/studio.py:1441-1444`).

## Why it matters

Stems use the mix's pre-limiter gain so they sum to the Mix (`src/naturalvoice/studio.py:1408`); removing ACX room tone breaks the noise-floor test (`tests/test_studio.py:264`).

## Connections

[[studio-render-options]], [[studio-parse-subtitles]], [[humanize-module]], [[entities/tts-module]]
