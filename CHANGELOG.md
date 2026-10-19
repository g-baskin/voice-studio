# Changelog

Notable changes to Voice Studio, grouped using Keep a Changelog categories.
The current source version is **0.3.0**. No Git tag or GitHub release has been published;
all entries below describe unreleased source, not historical releases.

## [Unreleased]

### Added

- Local voice cleanup, multi-voice Studio scripts, captions, dubbing, voice design and consent-gated cloning
  in the initial source snapshot (`7962b18`, 2026-10-18).
- Voice Studio branding, banner and app icons (`4e17b0f`).
- An optional environment settings example and explicit loading instructions (`bb599bd`).
- A build and manual release guide, with a regression check for product version consistency.
- Voice sample collections in Voice Lab: import a local audio or video file or one public YouTube video,
  review locally detected speakers with optional background separation, and save approved samples per
  person from multiple recordings. Build new cloning reference versions without replacing older ones,
  compare them on the same sentence and mark a preferred version. This improves the references used
  for cloning; it does not train a model (`0a207b3`).
- An optional, separately installed media engine for sample collections, set up with
  `scripts/setup_media_engine.sh`; the main and Chatterbox environments are not changed (`0a207b3`).

### Fixed

- Python's reported version and the macOS launcher's version now match the package's `0.3.0` source version.

[Unreleased]: https://github.com/g-baskin/voice-studio/commits/dev
