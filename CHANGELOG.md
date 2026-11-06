# Changelog

Notable changes to Shark Audio (formerly Voice Studio), grouped using Keep a Changelog categories.
The current source version is **0.3.0**. No Git tag or GitHub release has been published;
all entries below describe unreleased source, not historical releases.

## [Unreleased]

### Changed

- The product is now called Shark Audio across the app, docs, banner and desktop launcher. The new `sharkaudio`
  command joins `voicestudio` and `naturalvoice`, which keep working. The desktop bundle keeps its folder name.
- Pages have clean addresses (`/studio`, `/voice-lab`, `/samples`, `/backup`); old `.html` addresses redirect
  with their query intact.
- The whole interface is now SvelteKit 3 with Svelte 5 (`frontend/`): Clean, Speak, Studio, Voice Lab, sample
  collections and Backup. The hand-written HTML pages and their scripts are gone; behaviour, element ids and
  saved browser data (templates and the Studio draft) are unchanged.

### Added

- **Editor Clip mode** (`/editor?mode=clip`), for fast clipping over the same sequence ([guide](docs/editor-clip-mode.md)):
  - **Editing:** a source viewer with its own In/Out, three-point insert, overwrite, append and smart insert (with
    back-timing and V/A target tracks), lift and extract, and Q/W/E trims.
  - **Tools and playback:** ripple, roll and slide tools with a two-frame trim view, and J/K/L shuttle up to 8×.
  - **Organising:** subclips, and coloured markers with a marker list.
  - **Analysis:** silence removal with review, scene detection to markers or splits, and a "moments" list ranked
    by loudness, pauses and cuts (a sorting aid, not a prediction).
  - **Output:** 9:16 and 1:1 presets with manual reframing, and batch export of each marker range or subclip as
    its own file.
  - **Compatibility:** old sequences load unchanged. Silence, scene and moment analysis are cancellable
    background jobs that share the processing slot.
  - **Changed key:** J now shuttles backwards instead of stepping one frame; ← and → step frames.
- **Editor Shorts** in Clip mode ([guide](docs/editor-shorts.md)):
  - **Transcripts:** local English speech-to-text with word timings (NVIDIA Parakeet TDT 0.6B v2, CC-BY-4.0,
    installed separately with `scripts/setup_speech_model.sh`). You can edit words and delete them from the
    timeline.
  - **Clean up:** filler and pause removal, reviewed before anything is cut.
  - **Captions:** word-by-word captions in the preview and burned into exports, plus an SRT download.
  - **Hooks:** candidate Shorts that start and end on sentence boundaries, ranked by structure and pace, with
    optional AI reordering that sends only the hook texts.
  - **Playback fix:** reverse playback in the program viewer now stops at the start of the sequence.
  - **Caption spacing fix:** the highlighted pop word and the black outlines no longer run into neighbouring
    words; the preview and export use the same spacing.
  - **New direct dependency:** Pillow, which was already installed through another package.
- **Speak** (`/speak`): directed multi-speaker performances with inline directions, chunked recording that
  plays as it arrives, retakes, plain-language revisions and a joined download. Directions are reported as
  applied, approximated or unavailable. Inspired by Fish Audio's published design; no Fish Audio code or
  models are used.
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
