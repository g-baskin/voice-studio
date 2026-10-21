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

### Security

- The web app now refuses requests that do not come from this computer through `127.0.0.1`/`localhost`,
  so other websites can no longer reach it through a rebound DNS name or send it cross-site uploads.
- Phone mode (`serve --host 0.0.0.0`) prints a private access link; other devices must open it once before
  they can use the app. The link is saved owner-only in the data folder and stays the same across restarts;
  `serve --new-token` replaces it and signs out every device. Request logs hide it.

### Fixed

- Python's reported version and the macOS launcher's version now match the package's `0.3.0` source version.
- Cleanup jobs no longer pile up in the temporary folder: the oldest finished jobs and old leftovers are
  removed, and text-to-voice files are deleted once downloaded.
- Recording problems users can fix are recognised by error type rather than message wording, and
  unexpected Studio line failures are now logged.

[Unreleased]: https://github.com/g-baskin/voice-studio/commits/dev
