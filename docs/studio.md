# Studio

Multi-voice voice-over production, fully offline: write or paste a script, give each line a voice and a
delivery, render a mastered mix with captions, stems and a timeline. Page: `/studio`; API: `/api/studio`;
engine: `src/naturalvoice/studio.py`.

## Features
- **Line cards**: text, speaker name, voice (stock / Voice Lab `custom:` / `clone:`), delivery preset,
  speed 0.5–2×, pitch −4…+4 semitones (pedalboard PitchShift, only applied when non-zero), volume −24…+12 dB,
  pause after 0–10 s. Add, duplicate, move (buttons or Alt+↑/↓), delete.
- **Paste a script**: `NARRATOR: text` or `[Narrator] text`; untagged lines keep the last speaker. A cast table maps
  each speaker to a voice before importing (replace or append).
- **Pronunciation dictionary** (per project): whole word, case-insensitive. Value is a respelling (`Nginx → engine x`)
  or IPA between slashes (`GIF → /ɡɪf/`), spliced into Kokoro's phoneme input (`is_phonemes=True`). Captions keep
  the original word.
- **Line preview**, cached by a hash of text, voice, settings and the dictionary words it uses (repeats are instant).
- **Render job** with progress and cancel (stops after the current line). A failing line (e.g. missing voice, clone
  engine not installed) is skipped and listed, unless "Stop if any line fails" is on.
- **Outputs**: full mix; optional per-speaker stems (plus a music stem), all the same length and aligned, at the mix's
  pre-limiter gain; optional per-line clips; SRT + VTT captions; timeline JSON; ZIP of everything.
  WAV 24-bit, FLAC, or MP3 320 kbps (ffmpeg). 24 kHz native, or 44.1 / 48 kHz. Resampling doesn't add detail.
- **Music bed**: upload (≤ 200 MB; WAV/FLAC/MP3/M4A/AAC/OGG/Opus/AIFF), loop or stop, level (music RMS, dBFS),
  auto-ducking from a voice sidechain envelope (depth, attack, release, ~250 ms hold, starts slightly ahead of
  speech), fade in/out.
- **Polish** (off by default): the `light` humanize chain with room tone off, per line, before mixing.
- **Projects**: save / open / duplicate / delete as JSON in `DATA_DIR/projects` (validated on load; damaged files
  return a clear error). Browser draft autosave (localStorage). Renders this session list (last 8 kept).

## Write a script for me
A collapsible card above the script. Fields: topic, details (one point per line), type, tone, length (15/30/60/90 s
quick buttons or 10–300 s), up to 4 speakers (dialogue defaults to Host + Guest), optional call to action and
audience, and "Use emotion tags" (off by default; tags only sound in cloned voices). Backend: `/api/scriptgen`.
- The status line says which engine will write: your language model (and via what), or the **built-in outline
  writer**, which is a template that arranges your points, not an AI (set OPENAI_API_KEY or run Ollama for fully
  written scripts). With a model connected the Studio asks for `mode: auto`; otherwise `template`.
- **Surprise me (test script)** fills the fields from `/api/scriptgen/sample` for the chosen type and writes it, so you
  can try the app without a script. It works with no AI.
- The result is a preview, not yet in the project: title, engine badge, notes, estimated length against the target,
  editable speaker and text per line (remove any), and a cast table. Each speaker gets a different voice:
  starred voices first, then English stock voices alternating female and male, and speakers already in the
  project's cast keep their voice. **Use this script** replaces the lines (with a confirmation if the script has
  text) and sets the title if it was untitled; **Add to end** appends; **Write another version** regenerates;
  **Cancel** discards. Lines then autosave and save with the project like any others.
- Writing shows elapsed seconds and can be stopped (**Stop writing**). 400/429/503 and network errors are shown
  in plain words and never change the script.

### Connect AI
Inside the card. With no AI connected the status says so and a **Connect AI** panel explains that Shark Audio uses
OpenRouter (one key for many models; get one at https://openrouter.ai/keys) and that the key is stored only on this
computer, in the app's data folder. Paste the key (password field, no autocomplete or spellcheck) and optionally a
model (default `openai/gpt-4o-mini`), then **Connect**: `PUT /api/llm/key` checks it with a tiny real request
(up to ~30 s, busy state) and saves it. Errors from the provider (rejected key, no credit, offline) are shown as
plain text. On success the field is cleared, and the script writer and the rewrite panel's "Use a language model"
option switch over right away. Connected via a saved key shows "Connected: OpenRouter (key …abcd, model X)" plus
**Disconnect** (asks first, `DELETE /api/llm/key`). A key from the `OPENROUTER_API_KEY` environment variable is
reported as such and can't be removed from the page. The key is never written back into the page, localStorage,
URLs or the console (the browser test checks this).

## My styles (custom delivery)
"Save as my style" on a line captures its effective settings: speed (line × preset), pitch (line + preset),
gain (line volume + preset), the preset's pause multiplier and EQ bands, and the line's pause after. Stored in
`DATA_DIR/styles.json` (atomic write, validated on load, bad entries skipped, ≤ 100 styles). API:
`GET/POST /api/studio/styles`, `DELETE /api/studio/styles/<id>`. Styles appear in the delivery picker under
**My styles**. Choosing one copies it **by value** into the line (`delivery: "custom"`, `style: {...}`) and resets the
line's own speed/pitch/volume so it sounds as saved; a project keeps rendering if the style is later deleted
(the picker then shows it as "(saved with project)").

## Director's notes
A free-text note per line (≤ 200 characters). "What does this mean?" runs a keyword parser (no AI,
`studio.parse_note`) and shows **What I understood**, the resulting numbers and the words it couldn't use. Nothing
changes until you press **Apply**; every slider stays editable afterwards.
- Speed: slow/slower/slowly/unhurried (0.92×), much slower (0.85×), relaxed (0.95×, longer pauses), fast/faster/quick
  (1.08×), much faster (1.15×), rushed/urgent/hurried (1.12×, shorter pauses).
- Pitch: higher/brighter/lighter +1 st; lower/deeper/darker −1 st. Volume: softly/quiet/gentle −3 dB,
  whisper-soft −6 dB, louder/loud +3 dB, punchy/confident/bold +2 dB and 1.03×.
- Pauses: dramatic/long pause → 1.5 s after the line; beat → 0.8 s; quick pause/tight → 0.15 s and shorter pauses.
- "slightly / a bit / a little / a touch" halves the effects.
- Emotion words: for **clone voices** funny/amused → `[chuckle]`, laughing → `[laugh]`, tired/sigh → `[sigh]`,
  surprised → `[gasp]` (only if the clone engine lists that tag; otherwise the readout says so). For stock/custom
  voices they pick the nearest preset plus a small change: amused → Warm +0.5 st, tired → Soft 0.95× −0.5 st,
  surprised → Excited +0.5 st, laughing → Excited, sad → Soft 0.93× −0.5 st; warm/excited/energetic/calm/serious
  map to their presets. Only the first emotion picks the preset; others are reported as ignored.

## Emotion tags for cloned voices
When a line uses a `clone:` voice and `GET /api/clone/status` lists `emotion_tags`, a row of quick-insert buttons
puts the tag at the cursor. Those tags are not warned about and are passed to the clone engine unchanged
(it voices the 9 supported tags and strips others). Captions leave tags out: they are sounds, not words.
Measured (clone made from an 8.6 s Kokoro reference): "Well, that is funny." 1.82 s; "Well, [chuckle] that is
funny." 2.36 s (+0.54 s for the chuckle), no errors, caption "Well, that is funny.". On
stock voices `[tags]` other than pause/break are still read as text with a warning.

## Rewrite for speech
Per line and for the pasted script. Uses `POST /api/rewrite` (built-in rules; a language model only if
`/api/rewrite/status` says one is available, with a tone choice; otherwise the panel says to add OPENAI_API_KEY or
run Ollama). The result is shown as a word diff (removed in red, added in green) with the engine's notes; **Accept** or
**Keep original**. Nothing is overwritten silently. The rule engine keeps `[tags]` itself; the Studio also checks,
and if any rewrite (e.g. a language model) changed a tag, it rewrites only the text between tags and keeps every tag
exactly (defence in depth).

## Fit to time (ads, dubbing)
- **Project target** (15 / 30 / 60 s or custom): total file length, including head and tail silence. Order:
  1. re-synthesise unfitted lines with Kokoro speed scaled by the needed factor, capped at **0.85–1.2×**;
  2. fine-tune with pedalboard `time_stretch` (high quality, formants preserved), at most ±5% and never past the
     0.85–1.2× total;
  3. move inter-line pauses (each kept within 0.1–3 s, or its own value if already outside).
  If the target can't be reached inside those limits the result says **NOT met** with a warning; nothing is
  stretched further silently. Achieved length counts as met within max(0.1 s, 1%).
- **Per-line target** ("Fit this line to (s)"): same speed-then-stretch steps for that line only; it is then left
  alone by the project fit. Caption and timeline times follow the stretched audio.
- Example (browser test): 5.3 s script into 6 s: needs 0.84×, so speech was capped at 0.85× and pauses grew
  +0.18 s: achieved 6.0 s, met, with a warning about the cap.

## Dubbing: subtitle import, timed placement, video
- **Import subtitles** (Paste a script → "Or import subtitles"): `.srt` or `.vtt`, ≤ 2 MB. Each cue becomes a line
  with its `start`/`end`; formatting tags are dropped, `<v Name>` and upper-case `NAME:` become speakers. Bad blocks
  (no timing, unreadable or backwards times) are skipped with a warning; a file with no usable cues is rejected.
  Import switches the project to **Timed** placement.
- **Timed (dubbing) placement** (Project → Placement): each line starts exactly at its start time. Its slot is
  start..end (or start..next start if there's no end). A line longer than its slot is fitted with the fit-to-time
  steps (speed 0.85–1.2×, then ≤ ±5% stretch). If it still doesn't fit, nothing is cut: the result lists an
  **overlap** (runs into the next line's start) or **overrun** (past its own end, no overlap) per line, with seconds.
  Lines are never slowed to fill a slot. Captions and timeline use the placed timings. Project-level fit-to-time is
  ignored in Timed mode.
- **Dub a video** (Export → Dub a video): MP4/MOV/WebM/MKV ≤ 2 GB, streamed to disk; rejected if it has no picture.
  The dub track runs the full video length (speech past the end is kept and reported). Original audio: **replace**,
  or **keep it ducked** under the dub (level −40…+6 dB, using the music bed's ducking depth/attack/release; also a
  stem). Mux: `ffmpeg -c:v copy` (picture untouched), AAC 256k (Opus for WebM), and optionally a soft subtitle
  track (mov_text in MP4/MOV, WebVTT in WebM, SRT in MKV). Nothing is burned in; SRT/VTT sidecars are still exported.
  The dubbed video is in the result (player + download) and the ZIP. Uploads older than a day are deleted.
- **Voice Lab handoff**: `/studio?voice=<id>` puts that voice on the first empty line (or a new line) if the id
  is in the voice catalog; unknown ids are ignored. The parameter is then removed from the address bar.

## Alternate takes
"+ New take" on a line makes a variation from a new random seed (up to 5 per line; take 1 is the original). A
take changes: (a) the seeded natural speed jitter per phrase (±2%) and the pause jitter (±10%), and (b) for Kokoro
voices, a small seeded perturbation of the style vector (Gaussian noise at 3% of the style's spread), which shifts
timbre and intonation slightly. Same text, voice and settings otherwise. Clone voices only get (a) if the clone
engine varies. The chosen take ("Use this take") is saved in the project (`take`, `takes`) and used by the render;
the line cache is keyed by take, so switching back is instant.

## Keyboard shortcuts
⌘/Ctrl+S save project · ⌘/Ctrl+Enter preview the focused line · ⌘/Ctrl+Shift+Enter render · Alt+↑/↓ move line.
Also listed under "Keyboard shortcuts" on the page.

## Inline tags
| Tag | Effect |
|---|---|
| `[pause 1.5s]`, `[pause 300ms]` | Silence of that length, clamped to 0.1–10 s (with a warning) |
| `[break]` | Paragraph pause (1.2 s) |
| anything else in `[...]` | Read as text, and a warning is shown. Never silently dropped |

## Delivery presets
Kokoro has no emotion control, so presets are honest combinations of speed, pitch, pause length, gain and EQ:

| Preset | What it does |
|---|---|
| Neutral | Nothing |
| Warm | 5% slower, −0.5 st, +2.5 dB low shelf 220 Hz, −1.5 dB above 8 kHz, pauses +10% |
| Energetic | 10% faster, +0.5 st, +2 dB at 3 kHz, +1 dB, pauses −25% |
| Calm | 10% slower, pauses +30%, −1 dB, −2 dB above 6 kHz |
| Serious | 5% slower, −1 st, +1.5 dB low shelf 150 Hz, pauses +15% |
| Excited | 15% faster, +1 st, +2.5 dB at 3.5 kHz, +1.5 dB, pauses −35% |
| Soft | 8% slower, −3 dB, −3 dB above 5 kHz, pauses +20% |

## Delivery targets and measured results
Measured on a 30 s, 4-line, 2-voice script (af_heart + am_michael), 24 kHz WAV (ACX at 44.1 kHz). Integrated
loudness via pyloudnorm (BS.1770); true peak = 4× oversampled peak.

| Target | Spec | Measured | Result |
|---|---|---|---|
| YouTube / streaming | −14 LUFS, ≤ −1 dBTP | −14.53 LUFS, −1.10 dBTP | met (±1 LU) |
| Podcast | −16 LUFS, ≤ −1 dBTP | −16.24 LUFS, −1.23 dBTP | met |
| Broadcast EBU R128 | −23 LUFS, ≤ −1 dBTP | −23.00 LUFS, −2.75 dBTP | met |
| Audiobook ACX | RMS −23…−18 dBFS, peak ≤ −3 dBFS, noise floor ≤ −60 dBFS, 0.5–1 s head / 1–5 s tail room tone, 44.1 kHz MP3 ≥ 192 kbps CBR | RMS −20.07 dB, −3.37 dBTP; 0.75 s head, 2 s tail. With room tone (default for ACX) the floor is about −65 dBFS (test asserts −75…−60) | all met. Choosing ACX switches export to 44.1 kHz MP3 320 kbps CBR; the result warns if you change that |
| Raw | levels untouched | −22.8 LUFS, −2.55 dBTP | — |

Room tone: a steady warm noise bed (low-passed 600 Hz, high-passed 60 Hz) at −65 dBFS RMS added after mastering, on by default for ACX only (toggle "Room tone in pauses"). It goes into the mix, not stems.

YouTube sits about 0.5 LU under target because the limiter is kept gentle (it lands within ±1 LU). Every render
reports its own numbers, and says "Target NOT met" when a target isn't reached (e.g. very short or very peaky content).

## Render speed (Intel i5 Mac, CPU only, shared with other jobs)
- First render of 30 s of speech: 35–53 s (about 0.6–0.85× real time). Kokoro synthesis dominates.
- Re-render with changed export settings (lines cached): 4–6 s for 30 s (about 5–8× real time); ACX at 44.1 kHz: ~18 s.
- Browser test: 5.3 s of audio rendered in 6.2 s cold, 0.6–0.8 s from cache.

## Limits and validation
≤ 500 lines, ≤ 50,000 characters total (5,000 per line), ≤ 500 dictionary entries; all numbers must be finite and
within range; voice ids must be a stock name, `custom:<12 hex>` or `clone:<12 hex>`; project ids are 12 hex.
One CPU-heavy job runs at a time (shared `server.processing`); a second render or uncached preview gets HTTP 429.
Responses never include filesystem paths; scratch files live in the system temp dir and are pruned.

## Tests
`uv run pytest -q tests/test_studio.py` covers parsing, tags, dictionary, captions, ducking, mastering, a real Kokoro
render, projects, validation, 429, fit-to-time, takes and ACX room tone, SRT/VTT parsing, timed placement and overlaps, and video muxing (tiny lavfi test video). Browser: start `uv run voicestudio serve --port 8772`, then
`PLAYWRIGHT_MODULE=... node tests/browser_studio.cjs` (optional `NV_URL`).

## Command line
```
naturalvoice render project.json [-o outdir] [--target podcast|youtube|broadcast|acx|raw] [--format wav|flac|mp3]
                                 [--rate 24000|44100|48000] [--stems] [--video in.mp4 --video-audio replace|duck]
naturalvoice dub subs.srt|subs.vtt --voice <id> [--video in.mp4 --video-audio replace|duck] [--target ...] [-o outdir]
```
`render` takes a project JSON (the file the web app saves in `DATA_DIR/projects`, or a bare project object) and
validates it with the same rules as the API. `dub` imports the subtitles in Timed mode with one voice. Both write the
mix, captions, timeline, ZIP (and stems / dubbed video) to the output folder (default `<input>-render`), print
progress to stderr, and print a JSON summary to stdout: files, duration, target met, LUFS, true peak, RMS, noise
floor, warnings, per-line errors, overlaps and line fits. Exit code 0 = OK, 1 = rendered with line errors,
2 = invalid input. Default rate: 44.1 kHz for ACX, 48 kHz with a video, otherwise 24 kHz.
