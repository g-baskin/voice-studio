---
ai_description: |
  Pointer folder. Canonical Architecture Decision Records for this repo live in
  docs/adr/ (CLAUDE.md:5). Do NOT copy, move or renumber ADRs into this folder.
  Supersede accepted decisions in docs/adr/ rather than rewriting them.
human_description: |
  Index of the project's ADRs, which live in docs/adr/.
---

# Architecture decisions

The canonical ADRs live in [`docs/adr/`](../../../../docs/adr/), per `CLAUDE.md:5`. This folder only links to them; ADR files are not copied here.

| ADR | Title |
|---|---|
| [0001](../../../../docs/adr/0001-isolate-the-cloning-engine.md) | Isolate the cloning engine |
| [0004](../../../../docs/adr/0004-isolate-media-analysis-and-version-references.md) | Isolate media analysis and version clone references |

Numbering note: 0002 and 0003 never existed (`git log -- docs/adr` shows only the commits adding 0001 and 0004). The gap is historical; do not renumber.
