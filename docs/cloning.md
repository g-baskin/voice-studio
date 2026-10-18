# Zero-shot voice cloning

Speak any English text in the voice of a short reference recording (5–60 s), fully offline.

## Engine

The existing engine and isolation decision is recorded in [ADR 0001](adr/0001-isolate-the-cloning-engine.md).
See the [domain glossary](../CONTEXT.md) for the distinction between custom and cloned voices.

**Chatterbox-Turbo (ONNX)** by Resemble AI, about 350M parameters, English only. It is **MIT licensed**, so commercial use is allowed.
- Model: https://huggingface.co/ResembleAI/chatterbox-turbo-ONNX, pinned to revision `d21799bd0354adb85e348b8a0442a8405110a2cf`
- Upstream: https://github.com/resemble-ai/chatterbox

Why this engine: it is permissive, it runs on onnxruntime alone (no torch, so it works on Intel Macs), and it renders a 10 s sentence in under about 2 minutes on a 4-core i5. The ONNX export does **not** add the Perth watermark that the PyTorch package applies.

Candidates I did not benchmark here:
- XTTS-v2 (CPML, non-commercial)
- F5-TTS (CC-BY-NC weights)
- NeuTTS Air (needs llama.cpp)
- Zonos (needs torch ≥ 2.3; Intel Mac stops at 2.2)
- OpenVoice V2 tone conversion (lower quality)

## Install

```
scripts/setup_clone_engine.sh        # fp32, about 3.3 GB on disk (the default and the one tested)
scripts/setup_clone_engine.sh all    # also fetch the q8 files (+1.0 GB); not recommended, see below (q8 files were removed here)
```

The script is safe to re-run. It creates `engines/chatterbox/.venv` (Python 3.12, onnxruntime **1.23.2**, numpy 2, tokenizers) and downloads the model into `engines/chatterbox/models/`, checking each file's SHA-256. It also fetches the 26 MB WeSpeaker speaker-similarity model into `engines/eval/models/` (checksummed). The main app's onnxruntime 1.19.2 cannot load this model: it fails with "GroupQueryAttention softcap". That is why the engine lives in its own environment and runs as a persistent worker (`engines/chatterbox/worker.py`, JSON lines over stdin/stdout).

The worker loads once, takes about 15–28 s, and stops after 10 idle minutes.

Environment variables:
- `NATURALVOICE_CLONE_THREADS` sets the CPU threads (default 2).
- `NATURALVOICE_CLONE_IDLE` sets the idle timeout in seconds.

## Speed (i5-1038NG7, CPU, fp32)

| Test | Audio | Wall time |
|---|---|---|
| 4 threads, warm worker, one 21-word sentence | 6.3 s | 69 s (11 s per second of audio) |
| 2 threads, cold start (load included), "Hello there, nice to meet you." | 1.6 s | 47 s |
| 2 threads, browser preview "Nice to meet you." | 1.0 s | 62 s |

### fp32 vs q8 (warm worker, 2 threads, am_michael reference, "Good morning everyone, and thank you for joining us today.")

| Precision | Disk | Audio | Wall (warm) | s per s of audio | Similarity vs reference |
|---|---|---|---|---|---|
| **fp32** (default) | 3.3 GB | 2.96 s | **12.8 s** | **4.3** | 0.780 |
| q8 (dynamic int8) | +1.0 GB | 2.96 s | 126.5 s | 42.7 | 0.782 |

Both renders produced 2.96 s of audio and score the same similarity, but q8 is about 10× **slower** on this Intel CPU. onnxruntime's int8 kernels are slow here. So there is no precision setting: fp32 stays the only mode, and the q8 files are not needed.

Caveat: timings are noisy because other builders were using the same 4-core CPU at the same time. The q8 gap is far too large to be noise.

Most of the time goes to the autoregressive language model (about 0.16 s per token, about 25 tokens per second of audio) and the decoder. Plan on roughly 10 s of compute for each second of speech, plus a fixed cost of about 20 s.

## Similarity

Measured as speaker-embedding cosine with WeSpeaker ResNet34-LM (Apache-2.0, https://huggingface.co/Wespeaker/wespeaker-voxceleb-resnet34-LM), using `engines/eval/speaker_sim.py`. The reference was a 14.8 s clip of Kokoro `am_michael`.

| Compared with the am_michael reference | Cosine |
|---|---|
| Clone output (different text) | **0.80** |
| Kokoro am_michael itself (different text, upper bound) | 0.95 |
| Kokoro bm_george (different male voice) | 0.16 |
| Kokoro af_heart (female) | 0.08 |
| Clone of am_michael vs an af_heart reference | 0.06 |

The clone sits clearly on the reference speaker's side. Anything above about 0.5 is usually treated as the same speaker.

## Voice changer (speech-to-speech)

You record a performance and it comes back in a clone voice's timbre. Timing, intonation and emotion are kept.

**Recipe.** This follows upstream `ChatterboxVC.generate` in https://github.com/resemble-ai/chatterbox/blob/master/src/chatterbox/vc.py:
1. `s3_tokens = s3gen.tokenizer(source)`
2. `s3gen.inference(speech_tokens=s3_tokens, ref_dict=embed_ref(target))`

**How the shipped ONNX graphs support it:**
- `speech_encoder.onnx` takes `audio_values` (24 kHz) and returns `audio_features`, `audio_tokens` (S3, 25 per second), `speaker_embeddings` (192) and `speaker_features` (T×80).
- `conditional_decoder.onnx` takes `speech_tokens`, `speaker_embeddings` and `speaker_features` and returns `waveform`.
- Running the encoder on the **source** gives its tokens. Running it on the **target reference** gives the prompt tokens and speaker conditioning.
- The decoder is then fed `[target prompt tokens + source tokens + 3 silence tokens]` together with the target conditioning. This is the same layout TTS uses, so the decoder returns only the new part.

No language-model step is involved, which makes conversion faster than TTS. Sources longer than 10 s are split at the quietest 20 ms frame between 6 and 10 s into each part. With 20 s parts, a 23 s test lost the target timbre mid-part: the 8–17.6 s stretch scored 0.07 similarity and the whole clip 0.30. With 10 s parts it holds throughout. Each part reaches 20 ms past its cut, its output is pinned to the source length (the decoder keeps timing at 25 tokens per second), and neighbouring parts are joined with a **40 ms equal-power (sin/cos) crossfade**. Text-to-speech sentences get an 8 ms raised-cosine fade in and out before the inserted pauses, so there are no clicks at joins. Unit tests check that a phase-mismatched join that would click when simply butted together has no step after crossfading, and that fades into silence are click-free.

**Measured** (Kokoro af_heart performance of 7.0 s, target am_michael clone; noisy timings because other builders shared the CPU):

| Measurement | Value |
|---|---|
| Output length | 7.16 s (timing kept) |
| Time, warm worker, standalone | 18.4 s (2.6 s per second of audio) |
| Time through the web UI | 15.7 s for 7.18 s (2.2 s per second) |
| Similarity of output to target reference | **0.66** |
| Similarity of output to source speaker | 0.09 |
| Similarity of source to target (baseline) | 0.00 |

**Long source** (23.2 s af_heart performance, split into 4 parts at 6.1, 12.1 and 21.2 s):

| Measurement | Value |
|---|---|
| Output length | 23.24 s (exact) |
| Time, worker cold start included | 54.8 s (2.4 s per second of audio) |
| Similarity to target, whole clip | **0.69** (by section: 0.61, 0.67, 0.71) |
| Similarity to source speaker | 0.03 |

The voice moves almost completely to the target. Similarity is a little lower than with TTS (0.66 vs 0.78) because the source's prosody and accent carry through.

**API:**
- `POST /api/clone/convert` takes a multipart form: `voice`, `file` (1–60 s, same file types, up to 50 MB), and `consent=true` confirming rights to the performance and the target voice. It returns 202 `{job}`.
- Poll `GET /api/clone/convert/{job}` and fetch `/audio` when done. The job shapes match preview.
- It shares the processing lock, so it returns 429 while another job is running.

**UI:** section 3, "Voice changer", in the Clone panel. Upload or record a performance, pick a target voice, tick the rights consent, then convert. Players for the original and converted audio appear, with a download button.

## Emotion tags

Supported tags, written inline: `[clear throat] [sigh] [shush] [cough] [groan] [sniff] [gasp] [chuckle] [laugh]`.

This is the upstream `EVENT_TAGS` list in https://github.com/resemble-ai/chatterbox/blob/master/gradio_tts_turbo_app.py, used as in `example_tts_turbo.py`. Upstream `tts_turbo.py` tokenizes text with the plain HF tokenizer and does no special tag handling.

**How the ONNX build handles them.** In `tokenizer.json`, each tag is a single **added special token** (ids 50267–50275). For example, `[laugh]` encodes to `[50275]`, whereas an unknown `[bogus]` falls apart into 5 ordinary pieces (`[`, `b`, `og`, `us`, `]`) that the model would read aloud as text.

The tokenizer also contains style tokens: `[angry] [fear] [surprised] [whispering] [advertisement] [dramatic] [narration] [crying] [happy] [sarcastic]`. Upstream does not offer them, I haven't tested them, and they are not exposed.

**Measured** (am_michael clone, warm, 2 threads):

| Text | Length | Frames above −35 dB |
|---|---|---|
| `That's hilarious, anyway, let's go.` | 2.48 s | 69 % |
| `That's hilarious [laugh] anyway, let's go.` | 2.88 s | 60 % |
| `That's hilarious [chuckle] anyway, let's go.` | 2.80 s | 66 % |

**Spectrograms.** In the untagged render, "anyway" follows "hilarious" after a short gap. In both tagged renders, a quiet (about −35 to −50 dB), broadband, breathy segment of about 0.4–0.5 s appears at exactly the tag's position, with a few short pulses and no harmonic speech structure, before "anyway". That is consistent with a soft laugh or chuckle. The tag clearly produces a non-speech event in the right place, but it is subtle: a breathy laugh, not a loud one. Nobody has listened to it yet.

**App behaviour:**
- `clone.speak` and the `/api/clone/preview` endpoint keep supported tags. Spelling is normalised: `[LAUGH]` becomes `[laugh]`.
- Any other `[bracketed]` text is removed. The preview response and job status carry a `warning` naming what was removed.
- Text that is only tags is rejected.
- The sentence splitter never breaks inside a tag, and a lone trailing tag stays with the sentence before it.
- `GET /api/clone/status` lists `emotion_tags`, and the preview box has a row of buttons that insert a tag at the cursor.

## Other languages (no extra downloads)

Chatterbox-Turbo is English-only, but the voice changer's speech tokenizer is not language-specific. So `language=es|fr|it|pt` on `/api/clone/preview` (and `clone.speak_language`) works in two steps:
1. A **built-in Kokoro voice reads the text** in that language. The app picks a female or male voice from the clone's metadata `gender`, or estimates it from the reference pitch (median F0 below 165 Hz counts as male; am_michael measures 119 Hz, af_heart 197 Hz).
2. That audio is **re-voiced as the clone** with `convert`.

The default, `en`, keeps the direct Chatterbox path.

**What this is and isn't.** It is the built-in voice's pronunciation, accent and rhythm with the clone's timbre. It is **not** native multilingual cloning: the clone's own accent and speaking style do not carry over, and quality is capped by Kokoro's pronunciation in that language. Emotion tags are dropped in this mode. Kokoro has no French male voice, so French always starts from `ff_siwis`; the clone's timbre still replaces it.

**Measured** (am_michael clone as target; one short sentence each; noisy shared CPU):

| Language (source voice) | Source → output length | Envelope agreement | Similarity to target | Similarity to Kokoro source | Source vs target (baseline) | Time (warm) |
|---|---|---|---|---|---|---|
| Spanish (`em_alex`) | 5.10 → 5.10 s | 0.95 | **0.67** | 0.35 | 0.07 | 18.9 s (worker cold start) |
| French (`ff_siwis`) | 4.51 → 4.51 s | 0.99 | **0.59** | 0.16 | 0.07 | 5.8 s |

Envelope agreement is the share of 20 ms frames where output and source agree on speech vs silence above −35 dB.

The timbre moves to the clone, and the output keeps the source's timing and speech/silence pattern almost frame for frame. That is strong evidence the content, and so the language, is preserved. However, I have **not verified intelligibility**: there is no ASR here and nobody has listened yet. Italian and Portuguese use the same method but were not measured.

## Using it

- **Web:** open the Voice Lab "Clone a voice" panel (`web/clone.js` renders into `#clonePanel`). Upload a file or record one with the read-aloud script, tick consent, give it a name and create it, then preview.
- **API:** see the docstring in `src/naturalvoice/clone_api.py`. It covers `GET /api/clone/status`, `POST /api/clone/voices`, and `POST /api/clone/preview` plus polling `/api/clone/preview/{job}` and fetching `/audio`.
- **Everywhere else:** `clone:<id>` voices work through `tts.speak`, which covers Studio and the CLI. Long text is split into sentences and joined with natural pauses.

## Limits

- English only (the voice changer works on any speech, but the voices were trained on English).
- Slow: a minute of speech takes about 10 minutes.
- One render at a time, sharing the app's processing lock (busy requests get a 429).
- Reference handling: the app keeps the first 20 s after trimming silence, converts to mono 24 kHz, and normalises loudness to −20 LUFS. Clean, close-mic speech gives the best results.
- Speed control is a pitch-preserving time-stretch applied after rendering.

## Responsible use

Creating a voice requires `consent=true`, meaning "I own this voice or have permission to clone it". The time of consent is stored in the voice's metadata. Do not clone anyone without their permission, and do not use cloned voices to deceive people. Everything stays on this computer.

## Tests

- `uv run pytest -q tests/test_clone.py`: validation tests, plus one real render marked `slow` (about 40 s) that is skipped if the engine isn't installed.
- Browser check, with a server on port 8773:
  ```
  PLAYWRIGHT_MODULE=… node tests/browser_clone.cjs
  ```
