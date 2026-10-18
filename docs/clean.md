# Clean: fix robotic and echoey voices

The Clean page (and `voicestudio clean`) removes the metallic ringing, hollow echo and robotic buzz from AI voices in
audio or video. This guide has the details; the project overview is in the [README](../README.md).

## Command line and web

| Want | Do |
|---|---|
| Web app | `uv run voicestudio serve --open` → http://127.0.0.1:8765 |
| Desktop (Mac) | double-click `desktop/Voice Studio.app` |
| Phone | `uv run voicestudio serve --host 0.0.0.0`, open `http://<your-mac-ip>:8765` on the phone (same Wi-Fi), then "Add to Home Screen" |
| Fix a file | `uv run voicestudio clean ad.mp4` → `ad.natural.mp4` (audio or video; the picture is untouched) |
| Text to voice | `uv run voicestudio speak "Hello there!" --voice af_heart -o hello.wav` |
| List voices | `uv run voicestudio voices` |
| Measure a file | `uv run voicestudio analyze clip.wav` |
| Benchmark | `uv run voicestudio bench` (about 10 min; `--quick` = 1 voice, about 2 min) → `bench/REPORT.md`, listen in `bench/audio/` |
| Tests | `uv run pytest -q` |

Presets: `light` (freshly generated speech), `standard` (typical AI voice-over), `strong` (very echoey or robotic).
Fine-tune any stage: `--ai-clean --dereverb --demetal --deharsh --warmth --denoise --room-tone` (0 to 1).

Paid engines (optional): set `ELEVENLABS_API_KEY` or `OPENAI_API_KEY`, then use `--engine elevenlabs|openai`.
Their output goes through the same cleanup.

## Preview, compare, and process a queue

- Add up to **20 files**, each up to **500 MB**. Select one to work on, or process the queue sequentially.
  A failed file does not stop the rest; **Process queue** retries failed and queued files, skipping completed ones.
  **Stop after current file** leaves the remainder queued. Download each result or a ZIP of completed full files.
- Pick a start time and a **10, 15, or 20 second preview**. The server decodes only that section, although the
  browser still uploads the source file. Video previews are audio-only; full-file processing preserves the video.
- **Suggest a template** analyzes that same section. Recommendations are low-confidence heuristics based on
  ringing, quiet-frame energy, spectral flatness and decay estimates, not a trained diagnosis. Apply explicitly.
- **My saved templates** stores up to 30 named control sets in this browser's local storage. Reload and select
  one to reuse it; names are displayed as text. Clearing browser data removes them. Built-in templates stay intact.
- The shared **A/B player** switches between original and cleaned audio at the same position. Listening copies
  are matched by integrated loudness with peak headroom; downloads retain the processed file's actual level.
  If audio is too short/quiet to match reliably, the player says so. This is audio-only comparison, even for video.
- Results score the **actual exported file**, not the pre-encoding signal. Listener and voice-quality predictions
  cover at most the first 60 seconds of the selected result. Drops over 0.1 are flagged as a reason to listen,
  not a statistically established quality difference. Changes below 0.1 are labelled small.
- **Pause level is not echo**: silence, noise, room tone and dynamics affect it. Brightness is tonal balance,
  not a measure where lower is always better. Neither receives a good/bad colour.

The queue is session-only: keep the tab/server running and download results before restarting. Saved templates
persist separately. This remains a local, unauthenticated app, not a public hosting service. Keep the default
loopback binding; preview/analysis/result files remain in the system temporary directory. ZIP downloads are
removed after delivery. One server processing slot prevents simultaneous cleanup jobs from exhausting the CPU.

Browser smoke checks (requires an existing Playwright installation):

```sh
PLAYWRIGHT_MODULE='/path/to/playwright' node tests/browser_templates.cjs
PLAYWRIGHT_MODULE='/path/to/playwright' node tests/browser_workflow.cjs
```

The second check uses local generated test audio, verifies preview/suggestion/save/A-B/batch/ZIP flows,
and writes desktop/mobile screenshots to `/tmp/naturalvoice-workflow-*.png`.

## What the cleanup does

0. **AI cleanup** (GTCRN, a 48k-parameter speech-enhancement model, ONNX, CPU): removes room echo and
   artifacts. It runs at 16 kHz, so the app applies its per-band gain to the full-quality original
   instead of using its muffled output.
1. **Classic echo removal**: estimates how long the room rings, subtracts the predicted echo tail, then gently
   lowers what's left in the pauses. Dry voices are detected and left alone.
2. **Metallic tone removal**: finds resonances that stay at the same pitch in every frame (real voices
   move; artifacts don't) and notches them out. Smooths the flicker in the top band.
3. **De-harsh**: tames 4 to 9 kHz fizz on voiced sounds only, so natural "s" sounds stay crisp.
4. **Warmth**: a little low-mid body and very light saturation.
5. **Room tone**: a very quiet bed so pauses aren't dead digital silence.
6. **Loudness**: -16 LUFS with a gentle look-ahead limiter.

Text to voice also varies the speaking rate slightly from sentence to sentence and uses realistic pause
lengths for commas, sentence ends and paragraphs.

## Benchmark

`voicestudio bench` damages clean speech in realistic ways (simulated rooms, phase-loss "metallic"
resynthesis, resonant ringing, low-bitrate MP3, and all of them combined) and scores every method with:
- **DNSMOS** (Microsoft's predicted listener rating, 1-5),
- **PESQ** (ITU-T P.862.2) and **STOI** (intelligibility),
- the app's own echo and metallic measures.

Latest full run, averaged over all damaged cases, 3 voices:

| Method | Listener rating (OVRL) | Voice (SIG) | Background (BAK) | STOI | Echo dB | Metal dB |
|---|---|---|---|---|---|---|
| untouched | 2.63 | 3.00 | 3.48 | 0.839 | -61.7 | 3.01 |
| classic chain (before AI) | 2.56 | 2.89 | 3.52 | 0.861 | -68.2 | 1.80 |
| **app: standard** | **2.81** | 3.13 | 3.80 | 0.863 | -70.6 | 1.89 |
| app: strong | 2.79 | 3.10 | 3.82 | 0.864 | -72.1 | 1.56 |

## Setup notes

- `librosa` can't be installed on Intel Macs (no llvmlite build), so the DNSMOS mel spectrogram is re-implemented in numpy.
- Intel Macs: `onnxruntime` is pinned to 1.19.2 in `pyproject.toml`, because newer versions have no Intel-Mac build.
