# Speak: directed performances

Open **Speak** (`/speak`). Write a scene, direct it inline, and hear it chunk by chunk.

```text
Narrator: [calm] The harbour was quiet that night.
Mara: [whisper] Did you hear that?
Jonah: [excited] It's the boat! They made it back!
```

- **Speakers:** start a line with `Name:`. Lines without a name continue the current speaker; text before any
  name uses the **Narration** voice. Each speaker gets a voice you can change; built-in, custom and cloned
  voices all work. (Studio also accepts `[Name]`, but in Speak a leading `[word]` is always a direction.)
- **Directions:** `[whisper]`, `[excited]`, `[sad]`, `[slow]` and so on. A direction lasts until the next one,
  so `[excited] Big news! [calm] Breathe.` performs two moods. `[pause 1s]` and `[break]` add silence.
- **Honest readout:** every direction is listed under its chunk as **Applied**, **Approximated**, **Not
  available** or **Not recognised**, with what was actually done. The local voices have no emotion model, so
  `[whisper]`, `[sad]` or `[angry]` are performed with speed, pitch, loudness and tone, not true whispering or
  crying. ≈ marks these on the tag buttons.
- **Cloned voices:** sound tags such as `[laugh]` or `[sigh]` go straight to the cloning engine, which makes the
  sound. For built-in voices they become the nearest delivery or are reported as not available.
- **Chunks:** long turns are split at sentence ends, then clauses, then spaces, never inside a `[tag]`. Each
  chunk appears as soon as it is recorded.
- **Revise:** type a note on any chunk, such as `gentler, a bit sadder` or `much slower`, and press **Revise**.
  The readout says which words it understood and which it ignored. **Retake** records the same chunk again with
  a small natural variation. Every version is kept (up to 12); press one to hear it and use it.
- **Download performance** joins the chosen version of every chunk, with short pauses between sentences and
  longer ones between speakers.

Performances are kept in temporary storage for this session (the last 8). For a saved, editable project with
music, captions and loudness targets, use Studio.

## Where the ideas came from

Speak's directing workflow (speaker turns, inline natural-language tags, sentence-first chunking that protects
tags, streamed chunks, retakes and plain-language revisions) was designed after studying how Fish Audio's
open-source Fish Speech project presents these ideas. Shark Audio contains none of Fish Audio's code, model
weights or voices, and is not affiliated with or endorsed by Fish Audio. Audio comes from the local Kokoro and
Chatterbox engines, so it sounds like those engines with more control, not like Fish Audio's models.
