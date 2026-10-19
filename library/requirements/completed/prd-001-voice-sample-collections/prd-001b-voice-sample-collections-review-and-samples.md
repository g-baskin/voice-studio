# PRD-001b: People, review and samples *(Retroactive)*

> **Status:** Shipped. Parent: [PRD-001](./prd-001-voice-sample-collections-index.md)

## What was built

- **People.** A named person (1 to 60 characters) requires a permission confirmation (`src/naturalvoice/sample_library.py:267-278`; UI `src/naturalvoice/web/samples.html:65-68`).
- **Review UI.** Source picker, detected turn list, original and dialogue players, exact start/end inputs and a selection preview (`src/naturalvoice/web/samples.html:74-92`). Audio served only for completed sources (`src/naturalvoice/sample_library_api.py:236-242`).
- **Saving a sample.** Requires listening confirmation; 0.5 to 60 s; inside a completed source (`src/naturalvoice/sample_library.py:281-290`). Ranges overlapping a different detected speaker are rejected (`:291-297`; `tests/test_sample_library.py:221`, `235`). The user picks dialogue or original audio (`:299`; UI `src/naturalvoice/web/samples.html:89`). Silent selections are rejected (`:304-306`).
- **Measurements.** Each sample stores RMS level and a possible-clipping flag (`src/naturalvoice/sample_library.py:322-323`). These are measurements, not a quality or identity score (`docs/sample-collections.md`, Workflow).
- **Manual assignment.** The sample is attributed to the person the user chose (`src/naturalvoice/sample_library.py:311-321`).

## Not built

Automatic cross-source identity matching (ADR 0004 Alternatives). Editing a saved sample in place (`docs/sample-collections.md`, Workflow).
