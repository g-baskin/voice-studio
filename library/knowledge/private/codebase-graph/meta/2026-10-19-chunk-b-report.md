---
type: meta
title: "Chunk B run report (Studio and writing)"
created: 2026-10-19
updated: 2026-10-19
status: developing
tags:
  - meta
related: []
sources: []
---

# Chunk B run report

- Mode: document, partial_scan: true. Repo HEAD `0a207b37dc9809791194e8b796c9113351ebfb6e` on `dev`.
- Extraction: no tree-sitter, Hivemind driver or Deep Lake available. Python was parsed with stdlib `ast` (read-only, venv interpreter). `studio.js` and `studio.html` were read as source text; no JS AST.
- Prior state: codebase-graph area had no chunk B pages, so there were no contradictions.
- Pages: 15 entity pages and 2 concept pages, all new, created with exclusive-create (no overwrites). That is 2 above the 8 to 15 guide target. The small `*_api` routers for scriptgen and rewrite are folded into their module pages (`scriptgen-module`, `rewrite-module`); no separate `scriptgen-api-module` or `rewrite-api-module` page exists, although other pages link those names.
- Private helpers in studio.py (`_render_project_lines`, `_place_project_lines`, `_mix_project_tracks`, `_master_project_audio`, `_kokoro_phrase`) are described inside their callers' pages.

## Gaps

- `tts._kokoro`, `tts.speak`, `tts.split_chunks` (chunk A), `voices.resolve`, `voices.style_of`, `voices.DATA_DIR`, `clone.*` (chunk C), `server.processing` lock (chunk A): referenced but not defined in this chunk.
- `parse_note`, Delivery style routes and the pronunciation dictionary have no dedicated pages.

## ADR candidates (not filed; docs/adr is canonical)

- Delivery presets as speed, pitch, pause, gain and EQ because Kokoro has no emotion control (`src/naturalvoice/studio.py:3-4`).
- Timed placement keeps cue starts and reports overlaps instead of cutting (`src/naturalvoice/studio.py:1222-1251`).
- LLM provider order (OpenRouter, OpenAI, custom URL, Ollama) and keys never returned to the browser (`src/naturalvoice/llm.py:88-151`).
- One global processing lock, so a concurrent render returns 429 (`src/naturalvoice/studio_api.py:171-176`).
- Take as seeded Kokoro style-vector jitter (`src/naturalvoice/studio.py:709-712`).
