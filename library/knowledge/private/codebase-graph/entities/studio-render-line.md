---
type: entity
title: "studio.render_line"
entity_type: function
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/studio.py"
language: py
depends_on:
  - "[[entities/tts-module]]"
  - "[[voices-module]]"
  - "[[humanize-module]]"
  - "[[studio-module]]"
used_by:
  - "[[studio-render-project]]"
  - "[[studio-fit-project]]"
  - "[[studio-api-module]]"
last_commit_hash: "35c85ddcc30466e8280841dbdfaf7ceb0b22fcba"
tested_by:
  - "tests/test_studio.py:172"
  - "tests/test_studio.py:250"
tags:
  - entity
  - studio
related: []
sources:
  - "src/naturalvoice/studio.py"
---

# studio.render_line

## Overview

Renders one Line at 24 kHz and returns audio plus phrase timings in seconds (`src/naturalvoice/studio.py:685-686`).

## Signature

```py
def render_line(line: dict, dictionary: dict | None = None, polish: bool = False) -> tuple[np.ndarray, list[dict]]
```

## Behavior

- Cache lookup keyed by `line_key` (sha256 over text, voice, speed, pitch, volume, delivery, dictionary entries used, polish, take, custom style) (`src/naturalvoice/studio.py:645-662`, `:687-692`).
- Folds the Delivery preset or Delivery style via `delivery_of` into speed and pitch, clipped (`src/naturalvoice/studio.py:695-697`).
- Stock and custom voices: Kokoro via `tts._kokoro()` and `voices.resolve` (`src/naturalvoice/studio.py:705-708`). A nonzero Take perturbs the Kokoro style vector with seeded noise of `TAKE_STYLE_JITTER` (`src/naturalvoice/studio.py:709-712`).
- Cloned voices (`clone:` prefix) go through `tts.speak` and are resampled to 24 kHz (`src/naturalvoice/studio.py:702`, `:721-724`).
- Dictionary phoneme entries are spliced into the phoneme string in `_kokoro_phrase` (`src/naturalvoice/studio.py:665-682`).
- Raises `StudioError` if no words (`src/naturalvoice/studio.py:748-749`). Post: pitch, EQ (pedalboard), optional `humanize` "light" polish, gain (`src/naturalvoice/studio.py:750-755`).
- Stores result in LRU cache capped at 64 (`src/naturalvoice/studio.py:756-759`).

## Connections

- depends_on: [[entities/tts-module]], [[voices-module]], [[humanize-module]]
- used_by: [[studio-render-project]], [[studio-fit-project]], [[studio-api-module]] (`preview` route)
- concepts: [[studio-render-pipeline]]

## Tested by

- `tests/test_studio.py:172` (preview cached), `tests/test_studio.py:250` (takes differ)
