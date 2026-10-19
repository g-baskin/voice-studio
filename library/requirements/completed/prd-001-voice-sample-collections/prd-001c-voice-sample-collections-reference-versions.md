# PRD-001c: Reference versions and preference *(Retroactive)*

> **Status:** Shipped. Parent: [PRD-001](./prd-001-voice-sample-collections-index.md)

## What was built

- **Build.** 1 to 40 distinct samples, all belonging to the person, totaling 5 to 20 s (`src/naturalvoice/sample_library.py:334-344`), matching the Chatterbox conditioning limit (ADR 0004 Decision). Samples are resampled to 24 kHz with short fades and concatenated (`:346-354`).
- **Versioning.** Sequence is max existing `reference_version` + 1 (`src/naturalvoice/sample_library.py:355`), computed under the write lock; concurrent builds get distinct numbers (`tests/test_sample_library.py:299`).
- **Cloned voice.** Saved through the existing clone store as `<name> v<n>` with provenance metadata (`sample_person`, `sample_ids`, consent time, method) (`src/naturalvoice/sample_library.py:359-372`). It is a cloned voice, not a custom voice.
- **Listing.** Versions are clones whose metadata names the person (`src/naturalvoice/sample_library.py:329-331`).
- **Preference.** `activate` records the preferred version on the person only (`src/naturalvoice/sample_library.py:375-382`); it does not rewrite Studio projects. Comparison previews use the existing clone preview API (`src/naturalvoice/web/samples.js:210-217`). Rollback by reselecting an older version (`tests/test_sample_library.py:181`).

## Not built

Model training or fine-tuning (owner deferred; ADR 0004).
