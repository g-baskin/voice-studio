---
title: Documentation, library, wiki and code graph refresh: Ship Gate report
date: 2026-10-19
base_commit: 0a207b37dc9809791194e8b796c9113351ebfb6e
status: gates passed; awaiting owner approval before any commit
---

# Documentation refresh: Ship Gate report

Scope: documentation, Library, wiki entities, code graph and a functional check of the app after the
Voice sample collections feature (`0a207b3`). No application code changed. One tooling script was added:
`scripts/code_graph.py`.

## What changed

| Area | Files | Owner |
|---|---|---|
| User docs | `README.md`, `docs/voicelab.md`, `docs/cloning.md`, `docs/sample-collections.md` | technical-writing-craft-wasp-drone |
| Glossary and agent rules | `CONTEXT.md` (5 terms), `AGENTS.md` (media engine invariants) | technical-writing-craft-wasp-drone |
| Changelog | `CHANGELOG.md` (Unreleased, Added) | changelog-release-notes-wasp-drone |
| Library v2 and backwards PRD | `library/` READMEs, `requirements/completed/prd-001-voice-sample-collections/` | library-wasp-drone |
| Narrative knowledge | `library/knowledge/private/{architecture,data,operations,voices}/` | knowledge-wasp-drone |
| Wiki entities and concepts | `library/knowledge/private/codebase-graph/{entities,concepts,meta}/` | wiki-wasp-drone (3 chunks plus link reconciliation) |
| Code graph | `scripts/code_graph.py`, `.../codebase-graph/meta/code-graph.{json,md}` | orchestrator |

Corrections made during integration: three Library README seeds carried absolute local paths from a
template projection defect and were rewritten to repo-relative text; the codebase-graph README now
separates the generated code graph from the authored entity pages; PRD AC-3 wording and the README media
engine size were corrected after review.

## Gate 1: Security (security-wasp-drone)

Result: CLEAR, no findings at confidence 80 or above. Checked: secret patterns and env var values,
absolute local paths and private hosts in all changed files and `library/`, security-boundary claims
against `server.py`, `sample_library_api.py` and `cli.py`, and `scripts/code_graph.py` (parse only, no
exec or import of repo modules, writes only its two fixed outputs). Caveat: the security stinger targets
a different web stack, so general checks were used. Not checked: every line of every library page, every
cited consent line, git history or dependencies.

## Gate 2: Quality (quality-wasp-drone)

Result: CLEAR, one Low finding (PRD AC-3 wording), since fixed. Citation sample: 28 of 28 cited lines
support their claims. Wikilinks: 629, 0 dangling. Dashes: none in new text. Code graph check mode passes,
and one edge of each kind (spawns, serves, requests, imports, calls) was traced to source. Not checked:
the remaining citations, wiki claims without citations, live YouTube imports.

## Gate 3: Repository health (orchestrator, github-repo-health-stinger)

Mode: local clone only, scoped to this change; remote branch protection and repository settings were not
checked. Result: pass with notes.

- New files: 95 (93 Markdown, `code-graph.json`, `scripts/code_graph.py`). No `.DS_Store`, caches,
  temp or partial files. `git diff --check` is clean.
- `.gitignore` still excludes `data/`, `models/`, `engines/*/.venv/`, `engines/*/models/` and `.env`.
- Five empty Library folders (`knowledge/public/{overview,guides,faqs}`, `knowledge/private/standards`,
  the PRD `qa/` folder) will not be committed because Git does not track empty folders.
- `code-graph.json` is about 171 KB and changes whenever source changes; regenerate it in the same
  commit as code changes.
- Commit subjects mix styles; the latest uses Conventional Commits, so a `docs:` subject fits.
- CI (`.github/workflows/ci.yml`) is disabled at the owner's request; checks stay local.

## Functional verification (orchestrator)

| Check | Result |
|---|---|
| `npm run check` (lint, format, DOM types, mypy, tsc) | pass |
| `pytest`, full suite | 172 passed, 2 `test_clone.py` failures under machine load near 300 (170 s render timeout, then a lock held by that job) |
| `pytest tests/test_clone.py` rerun at normal load | 26 passed |
| Browser: templates, workflow, stars, Voice Lab, Studio, sample collections | pass |
| Browser: cloning panel (create, preview, voice changer, 390 px) | pass, via a temporary copy pointed at the throwaway server |
| `scripts/code_graph.py` check mode | current |

Browser checks ran against a throwaway server with temporary data and synthetic speech only; the main
app and the preview were not touched. `tests/web_templates.cjs` is driven by `tests/test_core.py`, not
run standalone.

## Open items for the owner

- At the owner's request, `npm run check` now runs `scripts/code_graph.py` in check mode, so a source
  change without a regenerated graph fails the checks.
- Reported but not fixed (code, out of scope): voice metadata is not written atomically; deleting a
  cloned voice can leave a stale preferred version; only `/api/samples` checks for a loopback peer;
  `/api/speak` runs outside the processing lock; the 2 GB sample budget excludes reference files under
  `voices/`; the macOS launcher log ignores `NATURALVOICE_DATA`; `browser_templates.cjs`,
  `browser_workflow.cjs` and `browser_clone.cjs` hardcode their ports. Most are documented with
  citations in `library/knowledge/private/architecture/system-overview.md`,
  `library/knowledge/private/data/storage-layout.md` and the other knowledge docs; the rest come from the
  knowledge drone's run notes and need confirmation before any fix.
- ADR numbers go from 0001 to 0004; 0002 and 0003 never existed. Nothing was renumbered.
