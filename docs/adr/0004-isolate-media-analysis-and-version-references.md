# 0004. Isolate media analysis and version clone references

Date: 2026-10-18

## Status

Accepted for the local feature implementation. Integration remains subject to owner approval.

## Context

Users want to collect a permitted person's speech from multiple recordings, inspect speaker turns,
remove accompaniment where possible, and improve cloning references later. The target Intel Mac
has no NVIDIA GPU. The owner selected local-only processing and explicitly deferred actual model
training. Root ONNX Runtime must remain at 1.19.2 and Chatterbox must keep its independent environment.

## Decision

We chose a third, isolated Python 3.12 media engine with pinned sherpa-onnx and yt-dlp packages.
The main app decodes a bounded audio window through FFmpeg, then invokes a one-job CPU subprocess.
Use pyannote segmentation, English 3D-Speaker embeddings and optional Spleeter vocal separation.
Keep all inputs and derived samples local. Permit canonical YouTube video links, not generic URL fetches.

Store immutable sources and reviewed samples in a new `sample-library` subtree of NATURALVOICE_DATA.
Publish JSON atomically after writing audio, serialize collection mutations with a filesystem lock,
and retain old reference WAVs. Each candidate is a new existing-library clone with sample provenance.
An explicit collection preference selects an existing version without rewriting Studio projects.
Select 5 to 20 seconds total per reference to match the existing Chatterbox conditioning limit.

## Consequences

- No root/cloning dependency changes or external upload of recordings.
- Adding samples expands a collection, not model weights. No training button or training claims.
- Original recordings, selected ranges and older references survive later additions.
- Speaker clustering is approximate and source-local; users assign each saved selection to a person.
- Vocal separation does not isolate simultaneous speakers. Detected overlaps are blocked, but absence
  of a flag is not proof of solo speech. Listening and permission confirmation remain mandatory.
- Imports are bounded to 250 MB, analysis to 120 seconds, and the collection store to a 2 GB budget.
  A movie larger than the upload limit must be clipped before import.
- JSON/audio publication can leave unreferenced new files after a crash, but cannot overwrite old data.
  Backups remain the owner's responsibility; no off-device recovery is configured by this feature.
- New endpoints are loopback-only and reject cross-origin browser requests. This is not authentication
  or a multi-user service. Run one local server per data directory.

## Alternatives considered

- Fine-tuning a GPU model or cloud training: deferred by the owner; needs separate engine, hardware,
  licensing, data-quality and privacy decisions.
- Add PyTorch/diarization dependencies to root: rejected because it risks existing Intel-Mac wheels.
- Overwrite the current clone when recordings arrive: rejected because quality can regress and existing
  projects should keep their chosen voice IDs.
- Automatic cross-source identity matching: deferred to avoid silently attributing a different person's
  voice. Manual assignment is the authoritative path in this version.
