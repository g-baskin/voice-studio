---
type: entity
title: "humanize.Settings, PRESETS and get_settings"
entity_type: data-model
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/humanize.py"
language: py
depends_on: []
used_by:
  - "[[entities/humanize-humanize]]"
  - "[[entities/server-app]]"
  - "[[entities/server-route-api-clean]]"
  - "[[entities/cli-main]]"
  - "[[entities/tts-speak]]"
  - "[[entities/bench-run]]"
  - "[[entities/workflow-process]]"
tested_by:
  - "tests/test_core.py"
last_commit_hash: "0a207b37dc9809791194e8b796c9113351ebfb6e"
tags:
  - entity
  - cleanup
related:
  - "[[concepts/cleanup-processing-pipeline]]"
sources: []
---

# humanize.Settings, PRESETS and get_settings

## Overview

Frozen dataclass of cleanup strengths plus the three cleanup presets (light, standard, strong) and the factory that builds a cleanup template from a preset with overrides (`src/naturalvoice/humanize.py:25-58`).

## Signature / Definition

```python
@dataclass(frozen=True)
class Settings:
    ai_clean: float = 0.0; dereverb: float = 0.8; demetal: float = 0.7
    deharsh: float = 0.6; warmth: float = 0.5; denoise: float = 0.0
    room_tone: float = 0.3; loudness: float = -16.0
    def to_dict(self) -> dict
PRESETS: dict[str, Settings]
def get_settings(preset: str = "standard", **overrides) -> Settings
```

## Behavior

- Fields are 0..1 strengths except `loudness` in LUFS (`humanize.py:27-34`).
- Presets: `light` disables AI cleanup and dereverb; `standard` is `ai_clean=1.0, dereverb=0.3`; `strong` raises every stage (`:44-51`). The comment records they were tuned with `naturalvoice bench` (`:40-43`).
- `get_settings` raises `ValueError` for an unknown preset and ignores `None` overrides (`:54-58`).
- Default `room_tone=0.3` is deliberate (ACX room tone invariant, see AGENTS.md); do not treat it as noise.
- Served as JSON by `GET /api/presets` (`src/naturalvoice/server.py:41-43`).

## Connections

- **depends_on:** none in chunk
- **used_by:** [[entities/humanize-humanize]], [[entities/server-app]], [[entities/server-route-api-clean]], [[entities/cli-main]], [[entities/tts-speak]], [[entities/bench-run]], [[entities/workflow-process]]
- **related concepts:** [[concepts/cleanup-processing-pipeline]], [[concepts/cleanup-job-lifecycle]]

## Tested by

- `tests/test_core.py`

## History

- **Scan HEAD:** commit `0a207b3` (`dev`), 2026-10-18. Per-symbol git history not traced in this partial scan.

## Sources

- `src/naturalvoice/humanize.py` (lines 25-58)
- `src/naturalvoice/server.py` (lines 34-43)
