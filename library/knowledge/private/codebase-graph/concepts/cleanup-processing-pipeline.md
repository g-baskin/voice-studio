---
type: concept
title: "Cleanup processing pipeline"
complexity: intermediate
domain: clean
aliases: [humanize chain]
created: 2026-10-19
updated: 2026-10-19
status: developing
tags:
  - concept
  - cleanup
related:
  - "[[entities/humanize-humanize]]"
  - "[[entities/humanize-settings]]"
  - "[[entities/enhance-ai-clean]]"
  - "[[entities/analyze-report]]"
  - "[[entities/workflow-process]]"
sources: []
---

# Cleanup processing pipeline

## Definition

The fixed-order DSP chain the Clean workspace applies to audio. A cleanup preset or cleanup template ([[entities/humanize-settings]]) configures it, and [[entities/humanize-humanize]] runs it (`src/naturalvoice/humanize.py:332-368`).

## How it works

1. AI cleanup via the GTCRN gain mask, only when enabled and the model exists ([[entities/enhance-ai-clean]], `humanize.py:336`).
2. Echo removal, metallic tone, harshness, artifact denoise, warmth (`humanize.py:337-341`).
3. Room tone, then loudness levelling with a soft limiter (`humanize.py:342-343`, `:310-326`).
4. Stereo is processed as mid plus a reduced side (`humanize.py:362-368`).

Callers wrap it: [[entities/workflow-process]] (Clean jobs), [[entities/cli-main]] `clean`, [[entities/tts-speak]] (light preset after synthesis, `src/naturalvoice/tts.py:146-147`) and [[entities/bench-run]] for tuning.

## Why it matters

Room tone is intentional and covered by the ACX tests (AGENTS.md). Removing it as noise breaks that invariant. Stage order is a contract: the progress labels come from this list (`humanize.py:335-351`).

## Connections

- **involves entities:** [[entities/humanize-module]], [[entities/quality-dnsmos]], [[entities/analyze-report]]
- **related concepts:** [[concepts/cleanup-job-lifecycle]]

## Sources

- `src/naturalvoice/humanize.py` (lines 1-14, 25-58, 332-368)
- commit `0a207b3` (scan HEAD)
