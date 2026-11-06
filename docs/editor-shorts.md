# Editor: Shorts (transcripts, captions and hooks)

Captions-first clipping in Editor Clip mode (`/editor?mode=clip`). The **Transcript**, **Captions** and
**Hooks** tabs sit in the clip tools panel next to Moments, Silences and the rest
([Clip mode guide](editor-clip-mode.md)). Speech-to-text runs on this computer. Engine:
`engines/media/transcribe.py`. App side: `src/naturalvoice/transcript.py` and `src/naturalvoice/captions.py`.
Preview drawing: `frontend/src/lib/editor/captions.ts`.

## Setup

Speech-to-text needs the separate media engine and a speech model. Run this once in the app folder:

```sh
scripts/setup_speech_model.sh
```

- **What it does:** a locked `uv sync` of `engines/media`, then a download of the speech model into
  `engines/media/models/asr/`.
- **Size:** about 661 MB to download. Keep about 1.4 GB free while it runs.
- **Checks:** every file comes from a pinned revision and is checked for its exact size and SHA-256.
- **Never automatic:** the app never runs this from a web page. Until it is installed, the Transcript tab shows
  this setup step.

### Model and attribution

The model is NVIDIA **Parakeet TDT 0.6B v2** (English), int8 ONNX export by the sherpa-onnx maintainer:
[csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8](https://huggingface.co/csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8),
revision `1ab9323565ddb038682214b292f588070a538ce2`. It is licensed under
[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/) by NVIDIA. The setup writes
`engines/media/models/asr/ATTRIBUTION.txt`, and the setup state in the app shows the same credit. The model
files are not part of this repository.

## Transcript

- **Transcribe** turns the open source clip's first audio track into words with timings. You can cancel it, and
  the result is saved with the media item (`transcript.json`), so it only runs once.
  - Only one analysis or transcription runs at a time.
  - Deleting a media item while it is being transcribed is refused.
- **Words:**
  - Click a word to move the source viewer there.
  - Shift-click, or Shift with the arrow keys, selects a range.
  - **F2** or a double-click edits a word. Enter saves and Escape cancels.
  - **Delete** cuts the selected words out of the sequence, closing the gap. Undo restores them.
  - The word list has one Tab stop. ←/→, Home and End move between words.
- **Re-transcribing.** Your corrections are kept. Transcribing an edited transcript again asks before it
  replaces it.
- **Clean up.** Nothing is cut until you choose it.
  - **Fillers:** "um", "uh", "er", "erm", "ah", "hmm" and "mm". Optionally also "like", "you know" and "I mean",
    which are off by default.
  - **Possible fillers:** the model often leaves out "um" and "uh". **Find possible fillers** therefore also lists
    gaps between words (0.25 s or longer) that are not silent. Each has a **Listen** button and a tickbox.
  - **Pauses:** shortens gaps between words that are longer than a threshold (default 0.6 s) down to a set length
    (default 0.25 s).
  - Each apply is one undo step, and it uses the same ripple cut as silence removal.

## Captions

- **Word by word.** Captions show a few words at a time, with the spoken word highlighted. They are drawn in
  the program viewer and burned into exports.
- **Which track.** Captions follow one audio track (by default, the first track with sound). Words are placed on
  the timeline through each clip's trims and speed, so cut words never appear. If you remove the track the
  captions follow, they go back to the first track with sound.
- **Settings:**
  - Style: pop, karaoke, bold or clean.
  - Font: sans bold, impact, rounded or system.
  - Size and position.
  - Words per page (1 to 8), the longest line, upper case, colour, highlight colour, outline and animation.
- **Download SRT** saves the captions as SubRip text for other editors. Premiere XML export does not carry
  captions.
- **Export.** When captions are on, the export dialog has **Burn in captions** (on by default).
  - Captioned exports are capped at 30 minutes and run a little slower.
  - Each frame reuses an image for its caption state, at most 5,000 distinct states.
- **Fonts** come from a fixed list of installed system fonts. On macOS these are Arial Bold, Impact, Arial
  Rounded Bold and Verdana Bold. On Linux it is DejaVu Sans Bold. The preview loads the same file as the
  export, so they match.
  - If the font file is missing, the preview uses the browser's sans-serif and the export uses Pillow's
    built-in font. Line breaks and size can then differ slightly between the preview and the export.

## Hooks

- **Find** ranks candidate Shorts from the transcript. Each one starts at the beginning of a sentence and ends
  at the end of one, within the length range you choose (default 15 to 90 s).
- **How they are ranked** ("ranked by structure and pace"):
  - The opening line: a question, "you", a number, or a contrast or curiosity word.
  - Speaking pace.
  - Few fillers and pauses.
  - Loudness.

  Scores are relative within the list. They are a sorting aid, not a prediction of views.
- **For each hook:**
  - **Open in source** sets the source In/Out to it.
  - **Add** appends it to the sequence.
  - **Add as subclip** saves it as a subclip.
- **Rank with AI** appears only when an AI provider is set up in Settings, and it names that provider.
  - It sends only the hook texts: at most 20, of 160 characters each.
  - It uses the reply only to reorder them. If the reply is unusable, the list keeps its own order.

## Keys (Clip mode)

| Key | Action |
| --- | --- |
| `T` | Open the Transcript tab |
| `⇧C` | Turn captions on or off |

## Limits

- **English only** with this model.
- **Speed:** roughly 3 to 10 times faster than real time on an Intel Mac CPU. A one-hour file can take 10 to 20
  minutes. Files over 4 hours are refused.
- **Not included:** face-tracked automatic reframing, split-screen layouts, B-roll, emoji or keyword highlight
  packs, and per-speaker colours.
