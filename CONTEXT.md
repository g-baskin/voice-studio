# Domain glossary

Voice Studio — The complete local voice-production application. Avoid: using Studio for the whole product.

Studio — The workspace for scripts, delivery, rendering, captions and dubbing.

Clean — The workspace for reducing unwanted artifacts in existing audio or video.

Voice Lab — The workspace for browsing, designing, matching and cloning voices.

Voice — A reusable identity used to synthesize or re-voice speech; distinct from the speaker role in a script.

Stock voice — A built-in Kokoro voice. “Built-in voice” is the plain-language equivalent; use stock voice when distinguishing voice categories.

Custom voice — A Kokoro voice created by blending, describing or matching stock voices. Excludes cloned voices. Avoid: using custom voice for every user-created voice.

Cloned voice — A voice based on a reference recording and used by the cloning engine. Not a blend or a close match among stock voices. Avoid: calling a matched custom voice a clone.

User-created voice — Either a custom voice or a cloned voice. Use this umbrella term when both categories are included. Avoid: custom voice as the umbrella term.

Voice vector — The numerical Kokoro representation that determines a voice's character. Also called a Kokoro style vector. Avoid: unqualified style when it could mean delivery settings.

Voice recipe — The weighted source voices and character controls used to construct a custom voice. Not the rendered audio or the resulting voice vector.

Voice matching — Approximating a recording's timbre within the stock-voice space. Does not reproduce all of the speaker's accent, rhythm or identity; it is not cloning.

Voice conversion — Re-voicing an existing performance in a cloned voice's timbre while retaining its timing and delivery. “Voice changer” is the user-facing feature name.

Speaker — A named role in a script, such as Host or Guest. Two speakers may use the same voice; a speaker is not a voice identity.

Cast — The assignment of voices to named speakers in a script.

Line — One script unit with text, a voice and delivery settings, optionally including a speaker and timing. Not necessarily one sentence.

Project — The saved Studio composition, including its lines, cast and pronunciation dictionary. A script is its textual content, not the whole project.

Delivery preset — A built-in combination of speed, pitch, gain, pause and equalization settings for a line. Avoid: cleanup preset when describing delivery.

Delivery style — A named, reusable set of delivery settings captured from a line. A saved project keeps its own copy, so deleting the reusable style does not change that project. Avoid: confusing a delivery style with a voice vector.

Cleanup preset — A base set of processing strengths for cleaning audio: light, standard or strong. Distinct from a delivery preset.

Cleanup template — A cleanup starting point that combines a cleanup preset with control settings or overrides. Saved templates retain the selected controls. Avoid: treating template and preset as interchangeable.

Take — A seeded rendering variation of one line with the same text, voice and settings. Selecting a take chooses which variation is used; it does not create a new voice.

Render — Producing audio and related outputs from a line or project. A preview renders a sample or selected part rather than the complete final output.

Stem — A time-aligned audio output for one speaker or the music bed. Not an individual line clip or the complete mix.

Mix — The combined voice and optional music output of a project.

Timed placement — Positioning lines at explicit times, such as imported subtitle cues. Sequential placement instead plays lines in order with pauses.

Dubbing — Producing speech aligned to subtitle timing, optionally combining it with a video's unchanged picture.
