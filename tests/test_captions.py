"""Captions: timeline placement, paging (shared fixture with the browser), drawing, frames and SRT."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from naturalvoice import captions as cap
from naturalvoice import editor as ed

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "caption_pages.json").read_text(encoding="utf-8"))
A = "a" * 32
B = "b" * 32


def seq(clips: list[dict], captions: dict | None = None, **kw) -> ed.Sequence:
    tracks = [
        {"id": "v1", "kind": "video", "name": "V1"},
        {"id": "a1", "kind": "audio", "name": "A1"},
        {"id": "a2", "kind": "audio", "name": "A2"},
    ]
    return ed.Sequence.model_validate(
        {"name": "Caps", "width": 320, "height": 180, "fps": 25.0, "tracks": tracks, "clips": clips}
        | {"captions": captions if captions is not None else {}}
        | kw
    )


def clip(cid: str, track: str, media: str, start: float, src_in: float, src_out: float, **kw) -> dict:
    return {"id": cid, "track": track, "media": media, "start": start, "source_in": src_in, "source_out": src_out} | kw


@pytest.mark.parametrize("case", FIXTURE["cases"])
def test_pages_match_the_shared_fixture(case):
    found = cap.pages(case["words"], case["words_per_page"], case["max_chars"])
    assert [{"t0": p["t0"], "t1": p["t1"], "text": " ".join(w[2] for w in p["words"])} for p in found] == case["pages"]
    for t, text in case["at"]:
        i = cap.page_at(found, t)
        assert (" ".join(w[2] for w in found[i]["words"]) if i >= 0 else "") == text


def test_timeline_words_follow_speed_trims_mutes_and_cuts():
    words = [[0.0, 0.4, "zero"], [1.0, 1.4, "one"], [2.0, 2.4, "two"], [3.0, 3.4, "three"], [4.0, 4.4, "four"]]
    s = seq(
        [
            clip("c1", "a1", A, 10.0, 0.9, 2.5, speed=2.0),  # "one", "two" at double speed
            clip("c2", "a1", A, 12.0, 3.9, 5.0),  # "three" removed by the cut between clips
            clip("c3", "a1", B, 20.0, 0.0, 5.0, muted=True),
            clip("c4", "a2", A, 0.0, 0.0, 5.0),
        ]
    )
    placed = cap.timeline_words(s, {A: words, B: words})
    assert placed == [[10.05, 10.25, "one"], [10.55, 10.75, "two"], [12.1, 12.5, "four"]]
    s.captions.track = "a2"  # type: ignore[union-attr]
    assert [w[2] for w in cap.timeline_words(s, {A: words})] == ["zero", "one", "two", "three", "four"]
    trimmed = seq([clip("c1", "a1", A, 0.0, 1.3, 3.1)])
    # Words whose centre falls outside the trim are dropped.
    assert cap.timeline_words(trimmed, {A: words}) == [[0.7, 1.1, "two"]]


def test_caption_track_prefers_sound_tracks_then_a_video_clip_with_its_own_sound():
    words = [[0.0, 0.4, "hello"]]
    picture = seq([clip("c1", "v1", A, 0.0, 0.0, 1.0)])
    assert cap.caption_track(picture) == "v1"
    assert cap.timeline_words(picture, {A: words}) == [[0.0, 0.4, "hello"]]
    both = seq([clip("c1", "v1", A, 0.0, 0.0, 1.0), clip("c2", "a2", B, 0.0, 0.0, 1.0)])
    assert cap.caption_track(both) == "a2"
    assert cap.caption_track(seq([clip("c1", "v1", A, 0.0, 0.0, 1.0, muted=True)])) is None


def test_font_files_come_only_from_the_allowlist():
    assert cap.font_file("../../etc/passwd") is None
    assert cap.font_file("/System/Library/Fonts/Supplemental/Arial Bold.ttf") is None
    found = cap.font_file("sans-bold")
    assert found is None or str(found) in cap.FONTS["sans-bold"]


def colours(image: Image.Image) -> set[tuple[int, int, int]]:
    rgba = np.asarray(image)
    return {(int(px[0]), int(px[1]), int(px[2])) for px in rgba[rgba[..., 3] == 255]}


def test_pop_style_highlights_the_active_word_inside_the_band():
    s = seq([], {"style": "pop", "color": "#ffffff", "highlight": "#ff0000", "uppercase": True})
    page = {"t0": 0.0, "t1": 1.0, "words": [[0.0, 0.3, "big"], [0.3, 0.6, "news"]]}
    caps = s.captions
    assert caps
    top, tall = cap.band(caps, 320, 180)
    assert (top, tall) == (112, 36)  # 11 px text, a 3.2x band rounded up to even, centred at 72%
    image = cap.draw_state(caps, 320, 180, page, 1, 2, cap.fonts_for(caps.font))
    assert image.size == (320, tall)
    seen = colours(image)
    assert (255, 255, 255) in seen and (255, 0, 0) in seen
    clean = cap.draw_state(caps.model_copy(update={"style": "clean"}), 320, 180, page, -1, 2, cap.fonts_for("impact"))
    assert (255, 0, 0) not in colours(clean)


def test_frames_hardlink_shared_states_and_respect_the_limits(tmp_path, monkeypatch):
    s = seq([], {"style": "pop"})
    found = cap.pages([[0.2, 0.5, "Hello"], [0.5, 0.9, "there."]], 3, 24)
    count = cap.render_frames(s, found, 0.0, 2.0, tmp_path)
    assert count == 50
    frames = sorted((tmp_path / "frames").iterdir())
    assert len(frames) == 50 and frames[0].name == "0000000.png"
    blank = tmp_path / "states" / "blank.png"
    assert frames[0].stat().st_ino == blank.stat().st_ino
    assert frames[-1].stat().st_ino == blank.stat().st_ino  # after the page has ended
    states = {f.stat().st_ino for f in frames}
    assert 3 <= len(states) <= 8  # blank plus pop steps of two words
    monkeypatch.setattr(cap, "MAX_STATES", 2)
    with pytest.raises(ed.EditorError):
        cap.render_frames(s, found, 0.0, 2.0, tmp_path / "again")
    with pytest.raises(ed.EditorError):
        cap.render_frames(s, found, 0.0, 31 * 60, tmp_path / "long")


def test_srt_lists_pages_with_timeline_times():
    found = cap.pages([[0.0, 0.5, "Hi"], [3661.25, 3661.5, "later."]], 3, 24)
    assert cap.srt(found) == "1\n00:00:00,000 --> 00:00:00,800\nHi\n\n2\n01:01:01,250 --> 01:01:01,800\nlater.\n"
