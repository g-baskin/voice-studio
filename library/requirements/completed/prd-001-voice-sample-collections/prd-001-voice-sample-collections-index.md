# PRD-001: Voice sample collections *(Retroactive)*

> **Status:** Shipped
> **Priority:** - *(retroactive - work is done)*
> **Written:** October 2026
> **Retroactive:** Yes - this PRD was written after implementation, from commit `0a207b37dc9809791194e8b796c9113351ebfb6e` on `dev`.
> **Schema changes:** Additive (new `sample-library` data subtree; clone metadata fields)

---

## What was built

A Voice Lab page (`src/naturalvoice/web/samples.html:42`, linked from `src/naturalvoice/web/voicelab.html:56`) where the user imports a permitted recording, reviews detected speaker turns, saves reviewed solo-speech samples into a per-person collection, and builds versioned reference recordings. Each reference version is a new cloned voice consumed by Chatterbox (`src/naturalvoice/sample_library.py:359-372`). This is reference selection, not training: the stored method is `reference-selection-not-training` (`src/naturalvoice/sample_library.py:370`); the owner deferred actual model training (`docs/adr/0004-isolate-media-analysis-and-version-references.md` Context and Alternatives).

## Goals

- Collect one permitted person's speech from multiple sources into one collection (`src/naturalvoice/sample_library.py:281-326`).
- Keep processing local and isolated from the root and Chatterbox environments (`scripts/setup_media_engine.sh:5-6`, `engines/media/worker.py:1`).
- Never overwrite older references; let the user pick a preferred version without rewriting Studio projects (`src/naturalvoice/sample_library.py:355`, `375-382`).

## Non-goals (NOT built)

- **Actual model training.** Owner deferred; no training code exists (`engines/media/worker.py:1`, `src/naturalvoice/sample_library.py:370`).
- **Automatic cross-source identity matching.** Speaker numbers are source-local; the user assigns each sample to a person manually (`src/naturalvoice/sample_library.py:281-290`; ADR 0004 Alternatives).
- **Per-person separation of simultaneous speech.** Spleeter separates vocals from accompaniment only (`engines/media/worker.py:35-62`); detected overlaps are blocked instead (`src/naturalvoice/sample_library.py:291-297`).
- Transcription, sample editing in place, destructive library management, backup or cloud sync (`docs/sample-collections.md`, Workflow and Data sections).
- **Live YouTube imports: unverified.** The code path exists (`src/naturalvoice/sample_library.py:179-217`) and URL validation is unit-tested (`tests/test_sample_library.py:104`, `117`), but no test or evidence in this commit performs a real download.

## Sub-features

| Sub-PRD | Scope | Status |
|---|---|---|
| [`prd-001a`](./prd-001a-voice-sample-collections-source-import.md) | Source import, decode, media engine analysis | Shipped |
| [`prd-001b`](./prd-001b-voice-sample-collections-review-and-samples.md) | People, review UI, saving samples | Shipped |
| [`prd-001c`](./prd-001c-voice-sample-collections-reference-versions.md) | Reference versions and preference | Shipped |
| [`prd-001d`](./prd-001d-voice-sample-collections-storage-and-boundaries.md) | Storage, locking, quota, loopback boundary | Shipped |

## Source workflow and evidence

**Source identity:** `voice-studio` at `0a207b37dc9809791194e8b796c9113351ebfb6e`.
**Template origin:** library-stinger `templates/prd-template.md`.
**Maintenance owner and review triggers:** repo owner; changes to `sample_library*.py`, `engines/media/`, or ADR 0004.

| Claim | Status | Locator | Verification owner |
|---|---|---|---|
| Behavior described in this PRD | SOURCE_OBSERVED | file:line citations throughout | library-wasp-drone |
| Fast API/persistence tests pass | NOT_RUN (by this drone) | `tests/test_sample_library.py` | quality-wasp-drone |
| Real-model smoke check | NOT_RUN; skips when engine absent (`tests/test_media_engine.py:15-16`) | `tests/test_media_engine.py:14` | quality-wasp-drone |
| Browser check | NOT_RUN | `tests/browser_samples.cjs` | quality-wasp-drone |
| Live YouTube download | UNKNOWN | none | owner |

## Acceptance criteria (as implemented)

| ID | Criterion | Evidence |
|---|---|---|
| AC-1 | Imports without permission confirmation are rejected. | `src/naturalvoice/sample_library_api.py:140-143`; `tests/test_sample_library.py:121` |
| AC-2 | Uploads over 250 MB are rejected before multipart spooling. | `src/naturalvoice/sample_library_api.py:53-59`; `tests/test_sample_library.py:140` |
| AC-3 | Selections containing detected overlapping turns of different speakers are rejected; consecutive turns by different speakers are not. | `src/naturalvoice/sample_library.py:291-297`; `tests/test_sample_library.py:221`, `235` |
| AC-4 | A reference requires 5 to 20 seconds total from one person's samples. | `src/naturalvoice/sample_library.py:340-344`; `tests/test_sample_library.py:206` |
| AC-5 | New versions never overwrite old ones; preference can roll back. | `src/naturalvoice/sample_library.py:355`, `375-382`; `tests/test_sample_library.py:181`, `299` |
| AC-6 | Non-loopback or cross-origin requests get 403. | `src/naturalvoice/sample_library_api.py:23-34`; `tests/test_sample_library.py:76`, `80`, `84` |

## Definition of Done checklist

- None; no project Definition of Done.

## API changes

All under `/api/samples`, router mounted in `src/naturalvoice/server.py:238` with upload middleware at `:232`. See [prd-001d](./prd-001d-voice-sample-collections-storage-and-boundaries.md) for the endpoint table.

## Contract dependencies

- None; no shared boundary identified.

## Open questions

- [ ] Live YouTube import has not been verified end to end.
- [ ] QA report not yet written (owned by quality-wasp-drone; target `qa/prd-001-voice-sample-collections-qa.md`).

## Related

- User doc: [`docs/sample-collections.md`](../../../../docs/sample-collections.md)
- ADR: [`docs/adr/0004-isolate-media-analysis-and-version-references.md`](../../../../docs/adr/0004-isolate-media-analysis-and-version-references.md), [`docs/adr/0001-isolate-the-cloning-engine.md`](../../../../docs/adr/0001-isolate-the-cloning-engine.md)
- Architecture index: [`library/knowledge/private/architecture/README.md`](../../../knowledge/private/architecture/README.md)
