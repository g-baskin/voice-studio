# Editor: Clip mode

A fast clipping workspace inside the Editor (`/editor`). Use the **Edit | Clip** switch in the header, or
**View > Clip mode**. Both modes share the same sequence, undo history and export. The choice is kept in the
browser and in the address (`/editor?mode=clip`). Engine: `src/naturalvoice/editor.py`; API: `/api/editor`;
pure edit functions: `frontend/src/lib/editor/timeline.ts`.

## Layout

- **Source viewer** (left of the program viewer). Double-click a bin item, or focus it and press Enter, to open it.
  - It has its own playhead, a filmstrip and waveform scrub bar, and its own In/Out marks.
  - **V** and **A** choose whether edits take the picture, the sound or both.
  - Subclips open with their marks already set.
- **Program viewer.** Its header has sequence size presets: 16:9 (1920 × 1080), 9:16 (1080 × 1920) and 1:1 (1080 × 1080). **Reframe** is next to them.
- **Clip tools panel** (replaces the Inspector), with tabs:
  - **Moments**
  - **Silences**
  - **Scenes**
  - **Markers:** jump, rename, colour or delete each one.
  - **Subclips:** make from the source In/Out, rename, open or delete.

Keys act on the **focused viewer**: click its title, or use it last. I, O, M, ⌥X, J/K/L, the arrows and Home/End
all follow that focus.

## Three-point editing

The source In/Out, the sequence In/Out and the playhead decide what goes where. A missing source In means the
start of the file, and a missing source Out means its end.

| Key | Edit |
| --- | --- |
| `,` | Insert at the sequence In, or at the playhead. Clips straddling that point are split, and every unlocked track moves along. |
| `.` | Overwrite. Whatever is under the new clip is trimmed or removed, and nothing else moves. |
| `⇧,` | Smart insert at the edit point nearest the playhead (no split). |
| `⇧.` | Append to the end of the sequence. |
| `;` / `'` | Lift (leave a gap) or extract (close it) between the sequence In and Out, on unlocked tracks. |
| `X` | Set the sequence In/Out to the clip under the playhead. |
| `⌘U` / `Ctrl+U` | Make a subclip from the source In/Out. |

- **Four points:** with a sequence In and Out and both source marks, the source is cut to the sequence span.
- **Reverse three-point:** with a sequence In and Out and only one source mark, the clip is back-timed. A lone source Out ends the clip on the sequence Out.
- **Target tracks:** the **V** and **A** toggles in the track headers choose them, one of each. Locked tracks cannot be targets. By default the targets are the first unlocked tracks.
- **After the edit:** the playhead moves to the end of the edit, and the whole edit is one undo step.

## Trimming

- **Ripple tool (B):** dragging an edge moves the later clips on that track.
- **Roll tool (N):** moves the cut between two neighbouring clips. The total length stays the same.
- **Slide tool (U):** moves a clip between its neighbours, which absorb the change. The clip keeps its own content.
- **Q / W:** ripple-trim the previous or next edit to the playhead. With ⌥, they trim without closing the gap.
- **E:** extends the selected clip's nearest edge to the playhead.
- **Limits:** every trim stops at the media's own length and skips locked tracks.
- **Trim view:** while you roll, ripple, slip or slide, the program viewer shows the outgoing and incoming frames side by side, with their timecodes.

## Shuttle

- **L / J:** play forwards or backwards. Pressing the same key again goes to 2×, 4× and 8×, and the other direction starts again at 1×.
- **K:** stops. Hold K and tap J or L to step one frame. ← and → also step one frame, or ten with Shift.
- **Reverse playback** is a series of quick seeks on the 540p preview. It looks steppy above 2× and plays no sound.

## Silences, scenes and moments

Analysis runs ffmpeg on the preview file as a background job with progress and **Cancel**. It shares the
processing slot with uploads and exports, so it waits (and says so) while one is running. Results are saved
beside the media and reused for the same settings.

- **Silences** (`silencedetect`):
  - **Settings:** threshold (dB), shortest pause and padding.
  - **Review:** every proposed cut is listed with a checkbox and a Go button, and **Remove** cuts the ticked ones in one undo step.
  - **What gets cut:** a cut is made only on tracks whose own clip is silent across it, including the linked picture or sound of the same clip. As with ripple delete, each cut closes up only its own tracks.
- **Scenes** (`select='gt(scene,X)'`): picture cuts in the file. They can be added as markers or used as split points.
- **Moments** are ranked windows (shortest and longest length in seconds, and how many to return).
  - **Score:** 0 to 100, relative to this file only. It combines loudness (EBU R128 momentary, `ebur128`), the share of time without pauses, and how often the picture cuts.
  - **Reasons:** each moment lists why it scored as it did, such as "loud, few pauses".
  - **Edges:** a moment starts after a nearby pause and ends before one, while staying within the length limits.
  - **Actions:** **Open in source** sets the source In/Out, and **Add** appends the moment.
  - **Limits:** the score is a sorting aid, not a prediction of views.

## Vertical video

- **Presets:** choose 9:16 or 1:1 in the program viewer's header.
- **Reframe:** shows a box over the selected (or topmost) clip.
  - **Drag:** moves the picture. Alt+drag scales it.
  - **Keys:** arrows move it by 1% (Shift: 10%), and ⌥↑/↓ scale it.
  - **Undo:** each drag or key press is one undo step.
- **Limits:** reframing is manual; there is no automatic face tracking.

## Batch export

The Export dialog offers **Each marker to the next** and **Each subclip in the sequence**. Each range becomes its own
MP4, named `<sequence>-<nn>-<label>.mp4` with the label reduced to letters, digits, spaces, `_ . -`.

- **Limits:** at most 50 files per batch. Subclips that are not in the sequence are skipped, and the dialog says how many.
- **Order:** files are rendered one at a time.
- **Cancel:** stops the rest of the batch. Finished files can still be downloaded.

## Saved data

- **Sequence:** subclips (`id`, `media`, `source_in`, `source_out`, `name` of up to 60 characters, `color`; up to 500) are saved with it, and markers gain a `color`.
- **Older saves:** these load unchanged, with no subclips and green markers.
- **Removing media:** media that a subclip uses cannot be removed from the bin, and neither can media that is being analysed.
- **Premiere Pro XML:** subclips and marker colours are not carried over.

## Not included

These need new models or dependencies and are left for an owner decision:
- transcript-based cutting and filler removal, which need offline speech-to-text with word times;
- automatic face-tracked reframing;
- ranking moments with a language model.

## Checks

- `uv run --locked pytest tests/test_editor.py` covers the models, the parsers on generated media, moment ranking, caching, the playlist guard and the API.
- `tests/browser_editor.cjs` covers Clip mode end to end. Run it against a server with disposable `NATURALVOICE_DATA` and point `NV_URL` at it. See [browser-tests.md](browser-tests.md).
