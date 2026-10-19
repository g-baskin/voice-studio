# Voice Lab

Open `voicelab.html` (Voice Lab in the top nav). Everything runs offline on this computer. Voices you make are
saved as `custom:<id>` in `data/voices` and can be used anywhere a voice id is accepted (Studio, CLI, `/api/speak`).

All Voice Lab voices live inside **Kokoro's style space**: a voice is a style array of shape (510, 1, 256), and
new voices are combinations and nudges of the 54 stock voices. Nothing here is a generative voice model or a
true clone (true cloning is in the Clone section, provided by a separate engine).

## Voice sample collections

To collect approved recordings of one person and build cloned-voice reference versions from them, use the
**Voice sample collections** link at the top of Voice Lab or in the Clone tab. See
[sample-collections.md](sample-collections.md). Collections produce cloned voices, not custom voices.

## Library
Lists stock voices, your voices and clones, with filters for language, gender and kind, plus search. Each voice
has **Preview**, which renders a fixed sample line in the voice's language. Previews are cached in `data/previews`,
so replaying one is instant. You can also copy the voice id or use **Use in Studio**, which opens
`studio.html?voice=<id>`. Your own voices also have **Rename**, **Delete** and (for designed voices) **Edit**,
which re-opens the saved recipe in Design.

## Design (blend)
Mix 2–5 voices (stock or your own). The weight sliders are normalised, so the shares always add up to 100%,
and the style is the weighted mean of the chosen styles. Save stores the normalised recipe in the voice's metadata
(`meta.recipe`) so it can be re-opened and edited. Saving an edited voice keeps the original and adds a new version.

### Character controls (kept only if measurement backs the label)
| Control | Method | Measured effect (median pitch, -1 / 0 / +1) |
|---|---|---|
| Masculine ↔ Feminine | adds `value × 0.5 × (mean female style − mean male style)` | am_michael 90 / 121 / 158 Hz; af_heart 169 / 200 / 233 Hz; bf_emma 153 / 185 / 216 Hz; bm_george 113 / 146 / 186 Hz |

Brightness (spectral centroid) rose with the slider for three of those four voices but **fell** for bm_george
(648 → 516 Hz). So the control is described as a pitch and gender-character control, not a brightness control.
No other control was kept, because none was measured to act consistently.

## Describe (keyword-based design)
You type something like "warm, deep male narrator, British" and can also set gender, accent/language, age feel
and energy. The words are matched against keyword lists, not passed to a generative model:
* gender words choose female or male stock voices; accent and language words pick the language prefix;
* deep / low / older and young / high / bright rank the candidates by **measured pitch**;
* warm / calm and crisp / energetic rank them by **measured brightness**.

**Generate 3 options** blends 2–3 of the top-ranked voices with random weights and a small random variation drawn
from the stock voices' spread. A gender hint is also applied. The UI shows what was understood (for example
"male, British English, lower pitch, warmer tone").

Pitch and brightness ship with the app in `src/naturalvoice/voicelab_features.json`. That file covers all 28
English stock voices (American and British), measured from a render of one 4 s line. To rebuild it (takes about
3 minutes):

```
uv run python scripts/build_voicelab_features.py        # English voices
uv run python scripts/build_voicelab_features.py abefhipjz   # every language
```

Pitch and tone words don't steer non-English voices, and the response says so.

## Match a voice from a recording (approximate)
1. Upload 10–60 s of one speaker (WAV, MP3, M4A or MP4, up to 100 MB). You must tick "I own this voice or have
   permission to use it"; the server rejects the request without it.
2. A speaker embedding (below) is computed from the recording with silence trimmed.
3. Each English stock voice's embedding of a fixed three-sentence line (about 14 s) ships with the app in
   `src/naturalvoice/voicelab_embeddings.npz`, so Match starts right away. The file stores a SHA-256 fingerprint of
   the Kokoro voices file, speaker model, measure line and feature version. If it doesn't match, Match measures
   the voices itself (about 6 min) and caches them in `data/cache`. Rebuild with
   `uv run python scripts/build_voicelab_embeddings.py`.
4. The top 3 stock voices by cosine similarity are blended, weighted by softmax over similarity. If the best
   single voice scores higher than that blend, matching starts from that voice instead.
5. A time-budgeted random walk (1/3/5/10 min, default 3) perturbs the style along the stock voices' directions.
   Each candidate is rendered and embedded, and only improvements are kept; the step size grows after a success
   and shrinks after a failure.
6. The result shows the before and after cosine scores, the closest stock voices, and players for the reference,
   the starting voice and the result. You can then save it as a custom voice, with the scores and consent stored
   in its metadata.

Only one heavy job runs at a time; a second gets HTTP 429 ("Another voice job is running…"). You can cancel at
any point.

**Honest limits.** This moves only timbre, within what Kokoro's voices can already express. Accent, rhythm,
breathing and the speaker's quirks don't carry over, and it is not a clone. With a 3-minute budget, the search
makes only about 13–17 attempts on this Mac, so the gains are small.

### How trustworthy is the score?
This table compares stock voices with each other: each voice read two different texts (rows: text A, columns:
text B), and the scores are cosine similarities of silence-trimmed 14 s renders.

| | af_heart | bf_emma | am_michael | bm_george |
|---|---|---|---|---|
| af_heart | **0.95** | 0.45 | 0.42 | −0.05 |
| bf_emma | 0.21 | **0.42** | 0.13 | 0.09 |
| am_michael | −0.11 | 0.04 | **0.30** | 0.11 |
| bm_george | −0.07 | 0.02 | 0.00 | **0.93** |

On average, the same voice scored 0.65 and different voices 0.10. In each row the same voice scored highest, but
some voices are close together. Treat the number as a guide, not proof.

Before the fix, short 4 s renders with silence left in did not separate voices at all.

### Real-world run (non-Kokoro reference)
The reference was 26 s of macOS `say -v Samantha`, matched with a 3-minute budget:
* Closest stock voices: af_sarah 0.683, bf_alice 0.626, af_kore 0.606. Matching started from af_sarah alone,
  because it beat the blend.
* After 184 s, 17 tries and 4 kept improvements, the score went from **0.683 to 0.711** (on the measure line).
* On an unseen sentence, the result scored 0.654 against the reference, up from 0.539 for the starting voice.

Sanity check, which is **inconclusive**:
* The result scored 0.585 against a different `say` voice (Daniel, male British) and 0.344 against a second,
  short (6 s) Samantha clip.
* The speaker model scores Daniel about as close to the Samantha reference (0.635) as another Samantha clip
  (0.628).

So on synthetic, non-Kokoro voices the score is weak evidence of a match. The refinement gives a small,
measurable gain in the model's score, but it doesn't prove the voice sounds like the speaker. The result is the
closest blend of the built-in voices; use the Clone tab for a true clone of a recording.

## Speaker model
* File: `models/3dspeaker_campplus_en_voxceleb_16k.onnx` (29.6 MB), CAM++ trained on VoxCeleb, 512-dim output.
  Input is 80-dim Kaldi-style log-mel fbank at 16 kHz (25 ms / 10 ms, povey window, mean-normalised), computed in
  numpy (`voicelab.fbank`).
* Download: https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_campplus_sv_en_voxceleb_16k.onnx
  (sherpa-onnx's export of the model).
* Upstream: https://www.modelscope.cn/models/iic/speech_campplus_sv_en_voxceleb_16k (model card license: "Apache
  License 2.0") from https://github.com/modelscope/3D-Speaker (LICENSE: Apache License 2.0).

## Timings (Intel i5 Mac, CPU only, measured)
| Step | Time |
|---|---|
| Kokoro render of a 4 s line (warm / first call) | ~3.4 s / ~10 s |
| Library preview, first play / cached | ~3–4 s / instant |
| Speaker embedding of one clip | ~0.6 s |
| One match-search attempt (14 s render + embedding) | ~13 s |
| Building shipped embeddings `voicelab_embeddings.npz` (28 voices, 14 s line) | 352 s (one-off, done before shipping) |
| Full 3-minute match on a 26 s reference | 184 s, 17 tries |
| Rebuilding `voicelab_features.json` (28 voices) | 170 s |

## API (`/api/voicelab`)
| Endpoint | Request | Response |
|---|---|---|
| `GET /library` | `?language=&gender=&kind=&q=` | `{voices, total, languages, controls}` |
| `GET /preview` | `?voice=id` | WAV |
| `GET /voices/{id}` | | record |
| `POST /voices/{id}/rename` | `{name}` | record |
| `DELETE /voices/{id}` | | `{deleted}` |
| `POST /design/preview` | `{recipe, text?}` | WAV |
| `POST /design/save` | `{recipe, name, kind: blend\|describe}` | record |
| `POST /describe` | `{prompt, gender, accent, age, energy, seed?}` | `{options:[{recipe, summary}]×3, understood, notes}` |
| `POST /match` | multipart `file`, `consent=true`, `budget` 5–600 | `{job}` |
| `GET /match/{job}` | | `{status, step, progress, similarity, elapsed, result?}` |
| `POST /match/{job}/cancel` | | `{status}` |
| `GET /match/{job}/audio` | `?which=before\|after\|reference` | audio |
| `POST /match/{job}/save` | `{name}` | record |

A recipe looks like `{voices:[{id, weight}] (2–5), controls:{gender:-1..1}}`. Every input is validated: weights
must be finite numbers, voice ids must exist, text is limited to 300 characters, and uploads are checked for type
and size. Error messages never include file paths.

## Tests
* `uv run pytest -q tests/test_voicelab.py`
* `uv run voicestudio serve --port 8771`, then
  `PLAYWRIGHT_MODULE=… node tests/browser_voicelab.cjs` (`NV_URL` overrides the address)

## Starring voices

Press the star next to any voice in the Library (stock, blended or cloned) to keep it handy.

- Starred voices float to the top of the Library, and **Kind → ★ Starred** shows only them.
- Studio's voice pickers and the Clean page's quick voice picker list a **★ Starred** group first
  (starred voices also stay in their normal group).
- Stars are stored in `data/favorites.json` (not in the browser), so every page and the command line share them:
  `naturalvoice voices --starred`. Deleting a voice removes its star. A damaged favourites file is ignored.
- API: `PUT /api/voicelab/voices/{id}/star` with `{"starred": true|false}`; `/api/voices` records carry `starred`.
