---
type: entity
title: "tts module (speech engines, MODEL_DIR, Kokoro loader)"
entity_type: module
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/tts.py"
language: py
depends_on:
  - "[[entities/humanize-module]]"
  - "[[entities/voices-module]]"
  - "[[entities/clone-module]]"
used_by:
  - "[[entities/cli-main]]"
  - "[[entities/server-app]]"
  - "[[entities/studio-module]]"
  - "[[entities/bench-run]]"
  - "[[entities/quality-dnsmos]]"
  - "[[entities/enhance-ai-clean]]"
  - "[[entities/voicelab-module]]"
last_commit_hash: "0a207b37dc9809791194e8b796c9113351ebfb6e"
tested_by: []
tags:
  - entity
  - voices
related:
  - "[[entities/tts-speak]]"
  - "[[concepts/studio-render-pipeline]]"
sources: []
---

# tts module (speech engines, MODEL_DIR, Kokoro loader)

## Overview

Text-to-speech entry module: offline Kokoro by default, with optional ElevenLabs, OpenAI and cloning engines (`src/naturalvoice/tts.py:1-7`). It also owns `MODEL_DIR`, the shared model directory other modules import (`tts.py:22`). The dispatcher `speak` has its own page: [[entities/tts-speak]].

## Signature / Definition

```py
MODEL_DIR = Path(os.environ.get("NATURALVOICE_MODELS", <repo>/models))
MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
PAUSE: dict[str, float]
@lru_cache(maxsize=1)
def _kokoro() -> Kokoro
def voices() -> list[str]
def split_chunks(text: str) -> list[tuple[str, float]]
def speak_kokoro(text, voice="af_heart", speed=1.0, seed=0) -> tuple[np.ndarray, int]
def speak_elevenlabs(text, voice, api_key) -> tuple[np.ndarray, int]
def speak_openai(text, voice, api_key) -> tuple[np.ndarray, int]
def speak(text, voice="af_heart", speed=1.0, engine="kokoro", humanize=True, settings=None)
```

## Behavior

- `MODEL_DIR`: `NATURALVOICE_MODELS` env var, else `models/` two levels above the package (`tts.py:22`). Imported by `enhance.py:19`, `quality.py:20` and lazily by `voicelab.py:160`, `voicelab.py:216`.
- `_kokoro()`: cached single Kokoro instance built from `kokoro-v1.0.onnx` and `voices-v1.0.bin` in `MODEL_DIR`; raises `RuntimeError` naming `MODEL_URL` when either file is missing (`tts.py:28-37`). Also called directly by `studio.py:707` and `clone.py:537`.
- `voices()`: sorted stock voice names from the loaded model (`tts.py:40-41`).
- `split_chunks`: splits text into phrases with pause lengths from `PAUSE` (`tts.py:25`, `tts.py:44-68`); reused by `studio.py:736`.
- `speak_kokoro`: resolves the voice via `voices.resolve` (`tts.py:75`), varies speed per phrase with a seeded RNG clipped to 0.5 to 2.0, inserts jittered pauses, raises `ValueError` on empty text (`tts.py:71-86`).
- `speak_elevenlabs` / `speak_openai`: HTTP PCM requests at 24 kHz with 120 s timeouts (`tts.py:89-110`).
- `speak`: routes `clone:` voices to the cloning engine, requires API key env vars for paid engines, pads and humanizes (`tts.py:113-148`); see [[entities/tts-speak]].

## Connections

- **depends_on:** [[entities/humanize-module]] (`tts.py:20`), [[entities/voices-module]] (`tts.py:72`), [[entities/clone-module]] (`tts.py:125`)
- **used_by:** [[entities/cli-main]] (`cli.py:126`), [[entities/server-app]] (`server.py:221`), [[entities/studio-module]] (`studio.py:693`), [[entities/bench-run]] (`bench.py:211`), [[entities/quality-dnsmos]], [[entities/enhance-ai-clean]], [[entities/voicelab-module]]
- **related concepts:** [[concepts/studio-render-pipeline]]

## History

- **Created:** commit `7962b18` by AutomationGod on 2026-10-18
- **Last touched:** commit `35c85dd` by AutomationGod on 2026-10-18

## Sources

- `src/naturalvoice/tts.py` (lines 1-148)
