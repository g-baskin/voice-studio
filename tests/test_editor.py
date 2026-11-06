"""Editor: media preparation, sequence rules, timeline export and Premiere XML."""

from __future__ import annotations

import subprocess
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import quote

import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from naturalvoice import audio as aio
from naturalvoice import editor as ed
from naturalvoice import voices

FF = aio._ffmpeg()


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(voices, "DATA_DIR", tmp_path / "data")
    return tmp_path / "data"


def make(path: Path, *lavfi: str, seconds: float = 3.0) -> Path:
    args = [FF, "-y", "-v", "error"]
    for source in lavfi:
        args += ["-f", "lavfi", "-i", f"{source}:d={seconds}" if "=" in source else f"{source}=d={seconds}"]
    if path.suffix == ".mp4":
        args += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest"]
    subprocess.run(args + [str(path)], check=True)
    return path


def add(path: Path) -> dict:
    record, dest = ed.new_media(path.name)
    dest.write_bytes(path.read_bytes())
    record.update(status="processing", size=dest.stat().st_size)
    ed.save_media(record)
    return ed.process_media(record["id"])


def clip(cid: str, track: str, media: str, start: float, src_in: float, src_out: float, **kw) -> dict:
    return {"id": cid, "track": track, "media": media, "start": start, "source_in": src_in, "source_out": src_out} | kw


def sequence(clips: list[dict], **kw) -> ed.Sequence:
    tracks = [
        {"id": "v2", "kind": "video", "name": "V2"},
        {"id": "v1", "kind": "video", "name": "V1"},
        {"id": "a1", "kind": "audio", "name": "A1"},
        {"id": "a2", "kind": "audio", "name": "Music", "duck": True},
    ]
    return ed.Sequence.model_validate(
        {"name": "Test cut", "width": 320, "height": 180, "fps": 25.0, "tracks": tracks, "clips": clips} | kw
    )


def frame_rgb(video: Path, at: float) -> np.ndarray:
    raw = subprocess.run(
        [
            FF,
            "-v",
            "error",
            "-ss",
            str(at),
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ],
        check=True,
        capture_output=True,
    ).stdout
    return np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).mean(axis=0)


def test_sequences_reject_overlaps_missing_tracks_and_odd_rates():
    m = "a" * 32
    with pytest.raises(ValidationError, match="overlap"):
        sequence([clip("c1", "v1", m, 0, 0, 2), clip("c2", "v1", m, 1.5, 0, 2)])
    with pytest.raises(ValidationError, match="missing track"):
        sequence([clip("c1", "nope", m, 0, 0, 2)])
    with pytest.raises(ValidationError, match="frame rate"):
        sequence([], fps=12.0)
    with pytest.raises(ValidationError, match="out point"):
        sequence([], range_in=4, range_out=2)
    ok = sequence([clip("c1", "v1", m, 0, 0, 2, speed=2), clip("c2", "v1", m, 1, 0, 2)])
    assert ok.duration == 3


def test_dissolve_is_centred_on_the_cut_and_limited_by_handles():
    vid = "a" * 32
    video: dict = {"id": vid, "kind": "video", "duration": 10.0, "has_audio": True}
    seq = sequence(
        [
            clip("c1", "v1", vid, 0, 0, 4),  # 6 s of handle after the out point
            clip("c2", "v1", vid, 4, 0.3, 4.3, transition={"duration": 2}),  # only 0.3 s before the in point
        ]
    )
    first, second = sorted((x for x in ed.plan(seq, {vid: video}) if x.picture), key=lambda x: x.t0)
    assert second.t0 == pytest.approx(3.7) and second.src0 == pytest.approx(0.0)
    assert second.fade_in == pytest.approx(0.6) and second.afade_in == pytest.approx(0.6)
    assert first.t1 == pytest.approx(4.3) and first.fade_out == 0 and first.afade_out == pytest.approx(0.6)


def test_pictures_fit_or_fill_the_frame():
    seq = sequence([])
    tall = {"width": 1080, "height": 1920}
    fit = ed.Clip.model_validate(
        {"id": "c", "track": "v1", "media": "a" * 32, "start": 0, "source_in": 0, "source_out": 1}
    )
    assert ed.placement(seq, fit, tall) == (102, 180, 109, 0)
    fill = fit.model_copy(update={"fit": "fill", "x": 0.25})
    w, h, x, y = ed.placement(seq, fill, tall)
    assert (w, h) == (320, 568) and x == 80 and y == -194


def test_speed_is_split_into_supported_tempo_steps():
    assert ed.atempo(4) == ["atempo=2", "atempo=2"]
    assert ed.atempo(0.25) == ["atempo=0.5", "atempo=0.5"]
    assert ed.atempo(1) == []


def test_media_is_prepared_with_proxy_filmstrip_and_waveform(tmp_path):
    record = add(make(tmp_path / "clip.mp4", "testsrc2=s=640x360:r=25", "sine=f=440", seconds=2))
    assert record["status"] == "ready" and record["kind"] == "video" and record["has_audio"]
    assert (record["width"], record["height"]) == (640, 360) and record["duration"] == pytest.approx(2, abs=0.1)
    folder = ed.media_dir(record["id"])
    assert (folder / "proxy.mp4").is_file() and (folder / "thumbs.jpg").is_file()
    assert record["thumbs"]["count"] == 2
    levels = ed.json.loads((folder / "peaks.json").read_text())["peaks"]
    assert abs(len(levels) - 100) <= 2 and max(levels) > 0

    sound = add(make(tmp_path / "tone.wav", "sine=f=220", seconds=1))
    assert sound["kind"] == "audio" and sound["duration"] == pytest.approx(1, abs=0.05) and not sound["has_video"]
    still = add(make(tmp_path / "still.png", "color=c=blue:s=64x48", seconds=0.04))
    assert still["kind"] == "image" and still["duration"] is None and (still["width"], still["height"]) == (64, 48)


def test_unsupported_files_are_refused():
    with pytest.raises(ed.EditorError, match="Use a video"):
        ed.new_media("notes.txt")


def test_export_layers_tracks_mixes_sound_and_keeps_the_limit(tmp_path):
    red = add(make(tmp_path / "red.mp4", "color=c=red:s=320x180:r=25", "sine=f=300", seconds=4))
    blue = add(make(tmp_path / "blue.mp4", "color=c=blue:s=320x180:r=25", "sine=f=500", seconds=4))
    loud = add(make(tmp_path / "loud.wav", "aevalsrc=0.99*sin(2*PI*200*t)", seconds=4))
    seq = sequence(
        [
            clip("c1", "v1", red["id"], 0, 0, 4, volume=6),
            clip("c2", "v2", blue["id"], 2, 0, 2),  # above V1 from 2 s; nothing on V2 before that
            clip("c3", "a1", loud["id"], 0, 0, 4, volume=6),
        ]
    )
    out = tmp_path / "out" / "cut.mp4"
    ed.render(seq, out, False, "draft", lambda f: None, threading.Event())
    assert ed.probe(out)["duration"] == pytest.approx(4, abs=0.1)
    before, after = frame_rgb(out, 1.0), frame_rgb(out, 3.0)
    assert before[0] > 200 and before[2] < 60, "V1 must show until the V2 clip starts"
    assert after[2] > 200 and after[0] < 60, "V2 must cover V1 once it starts"
    sound, _ = aio.load(out)
    assert np.abs(sound).max() < 0.95, "the limiter must keep the mix from clipping"


def test_export_ducks_music_and_honours_the_in_out_range(tmp_path):
    voice = add(make(tmp_path / "voice.wav", "aevalsrc=0.5*sin(2*PI*400*t)", seconds=2))
    music = add(make(tmp_path / "music.wav", "aevalsrc=0.3*sin(2*PI*100*t)", seconds=6))
    clips = [clip("v", "a1", voice["id"], 2, 0, 2), clip("m", "a2", music["id"], 0, 0, 6)]
    seq = sequence(clips, duck_db=18, range_in=1, range_out=5)
    out = tmp_path / "ranged.mp4"
    ed.render(seq, out, True, "draft", lambda f: None, threading.Event())
    assert ed.probe(out)["duration"] == pytest.approx(4, abs=0.1)
    data, sr = aio.load(out, sr=48000)
    mono = data.mean(axis=1)

    # Output 0-1 s is music alone; the voice starts at output 1 s. One-second windows put 100 Hz in bin 100.
    def band(start: float) -> float:
        return float(np.abs(np.fft.rfft(mono[int(start * sr) : int(start * sr) + sr]))[100])

    assert band(1.5) < band(0.0) * 10 ** (-9 / 20)


def test_cancelled_exports_leave_no_file(tmp_path):
    long = add(make(tmp_path / "long.mp4", "testsrc2=s=320x180:r=25", "sine=f=300", seconds=20))
    seq = sequence([clip("c", "v1", long["id"], 0, 0, 20)])
    cancel = threading.Event()
    cancel.set()
    out = tmp_path / "cancelled.mp4"
    with pytest.raises(ed.Cancelled):
        ed.render(seq, out, False, "high", lambda f: None, cancel)
    assert not out.exists()


def test_premiere_xml_has_tracks_dissolves_levels_and_markers(tmp_path, monkeypatch):
    monkeypatch.setattr(voices, "DATA_DIR", tmp_path / "my data")
    a = add(make(tmp_path / "a b.mp4", "testsrc2=s=320x180:r=25", "sine=f=300", seconds=4))
    seq = sequence(
        [
            clip("c1", "v1", a["id"], 0, 0, 2, volume=-6),
            clip("c2", "v1", a["id"], 2, 2.5, 4.0, transition={"duration": 0.8}, speed=2),
        ],
        markers=[{"time": 1, "label": "Hook <1>"}],
    )
    root = ET.fromstring(ed.premiere_xml(seq, ed.media_for(seq)).split("\n", 2)[2])
    video_tracks = root.findall("./sequence/media/video/track")
    assert len(video_tracks) == 2 and not video_tracks[1].findall("clipitem")  # V1, the bottom track, comes first
    v1 = video_tracks[0]
    spans = [tuple(int(c.findtext(k) or -1) for k in ("start", "end", "in", "out")) for c in v1.findall("clipitem")]
    assert spans == [(0, 50, 0, 50), (50, 69, 31, 50)]
    assert v1.findtext("clipitem[2]/filter/effect[effectid='timeremap']/parameter/value") == "200"
    dissolve = v1.find("transitionitem")
    assert dissolve is not None and (dissolve.findtext("start"), dissolve.findtext("end")) == ("40", "60")
    assert "/my%20data/editor/media/" in (v1.findtext("clipitem/file/pathurl") or "")
    level = root.findtext(".//filter/effect[effectid='audiolevels']/parameter/value")
    assert float(level or "nan") == pytest.approx(10 ** (-6 / 20), abs=1e-3)
    assert root.findtext("./sequence/marker/name") == "Hook <1>"


def client() -> TestClient:
    from naturalvoice import server

    return TestClient(server.app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000))


def wait_ready(c: TestClient, media_id: str) -> dict:
    for _ in range(300):
        record = c.get(f"/api/editor/media/{media_id}").json()
        if record["status"] != "processing":
            return record
        time.sleep(0.1)
    raise AssertionError("media never became ready")


def test_api_uploads_saves_exports_and_protects_used_media(tmp_path):
    c = client()
    source = make(tmp_path / "talk.mp4", "testsrc2=s=320x180:r=25", "sine=f=300", seconds=2)
    assert c.post("/api/editor/media?name=notes.txt", content=b"x").status_code == 400
    too_big = c.post("/api/editor/media?name=a.mp4", content=b"x", headers={"content-length": str(ed.MAX_BYTES + 1)})
    assert too_big.status_code == 413
    r = c.post("/api/editor/media?name=../../talk.mp4", content=source.read_bytes())
    assert r.status_code == 201 and r.json()["name"] == "talk.mp4"
    media = wait_ready(c, r.json()["id"])
    assert media["status"] == "ready", media
    assert c.get(f"/api/editor/media/{media['id']}/proxy", headers={"range": "bytes=0-9"}).status_code == 206
    assert c.get(f"/api/editor/media/{media['id']}/thumbs").headers["content-type"] == "image/jpeg"

    body = sequence([clip("c1", "v1", media["id"], 0, 0, 2)]).model_dump()
    created = c.post("/api/editor/sequences", json=body).json()
    assert [s["id"] for s in c.get("/api/editor/sequences").json()] == [created["id"]]
    assert c.put(f"/api/editor/sequences/{created['id']}", json=body | {"name": "Renamed"}).json()["name"] == "Renamed"
    assert c.put(f"/api/editor/sequences/{'f' * 32}", json=body).status_code == 404
    assert "Renamed" in c.delete(f"/api/editor/media/{media['id']}").json()["detail"]
    xml = c.get(f"/api/editor/sequences/{created['id']}/premiere.xml")
    assert xml.status_code == 200 and 'filename="Renamed.xml"' in xml.headers["content-disposition"]

    job = c.post("/api/editor/exports", json={"sequence": body, "quality": "draft"}).json()
    for _ in range(300):
        status = c.get(f"/api/editor/exports/{job['id']}").json()
        if status["status"] != "running":
            break
        time.sleep(0.1)
    assert status["status"] == "done", status
    assert c.get(f"/api/editor/exports/{job['id']}/file").content[4:8] == b"ftyp"

    assert c.delete(f"/api/editor/sequences/{created['id']}").status_code == 204
    assert c.delete(f"/api/editor/media/{media['id']}").status_code == 204
    assert c.get("/api/editor/media").json() == []


def test_export_refuses_missing_media():
    r = client().post(
        "/api/editor/exports", json={"sequence": sequence([clip("c", "v1", "b" * 32, 0, 0, 1)]).model_dump()}
    )
    assert r.status_code == 400 and "missing" in r.json()["detail"]


def test_editor_page_is_served():
    r = client().get("/editor")
    assert r.status_code == 200 and "Editor" in r.text


@pytest.mark.parametrize(
    "payload",
    [
        "#EXTM3U\n#EXT-X-TARGETDURATION:1\n#EXTINF:1,\nhttp://127.0.0.1:9/x.ts\n#EXT-X-ENDLIST\n",
        "ffconcat version 1.0\nfile /etc/hosts\n",
    ],
)
def test_playlists_disguised_as_video_are_refused(tmp_path, payload):
    fake = tmp_path / "clip.mp4"
    fake.write_text(payload)
    with pytest.raises(ed.EditorError):
        add(fake)
    assert not (ed.root() / "media").is_dir() or not list((ed.root() / "media").rglob("proxy.mp4"))


def test_export_includes_still_images(tmp_path):
    still = add(make(tmp_path / "green.png", "color=c=green:s=64x48", seconds=0.04))
    seq = sequence([clip("s", "v1", still["id"], 0, 0, 2, fit="fill")])
    out = tmp_path / "still.mp4"
    ed.render(seq, out, False, "draft", lambda f: None, threading.Event())
    assert ed.probe(out)["duration"] == pytest.approx(2, abs=0.1)
    rgb = frame_rgb(out, 1.0)
    assert rgb[1] > 100 and rgb[0] < 60 and rgb[2] < 60


def test_input_guard_stops_ffmpeg_following_a_playlist_to_other_files(tmp_path, monkeypatch):
    make(tmp_path / "private.wav", "sine=f=440", seconds=1)
    disguised = tmp_path / "clip.mp4"
    disguised.write_text("ffconcat version 1.0\nfile 'private.wav'\n")
    assert not ed.probe(disguised)["audio"]
    monkeypatch.setattr(ed, "INPUT_GUARD", [])
    assert ed.probe(disguised)["audio"], "without the guard ffmpeg reads the referenced file"


def test_sped_up_still_image_fills_its_clip(tmp_path):
    still = add(make(tmp_path / "blue.png", "color=c=blue:s=64x48", seconds=0.04))
    seq = sequence([clip("s", "v1", still["id"], 0, 0, 4, speed=2, fit="fill")])
    out = tmp_path / "fast-still.mp4"
    ed.render(seq, out, False, "draft", lambda f: None, threading.Event())
    assert frame_rgb(out, 1.8)[2] > 150, "the image must last the whole 2 s clip"


def test_premiere_xml_leaves_out_muted_sound(tmp_path):
    tone = add(make(tmp_path / "tone.wav", "sine=f=300", seconds=2))
    seq = sequence([clip("on", "a1", tone["id"], 0, 0, 1), clip("off", "a1", tone["id"], 1, 0, 1, muted=True)])
    root = ET.fromstring(ed.premiere_xml(seq, ed.media_for(seq)).split("\n", 2)[2])
    assert len(root.findall("./sequence/media/audio/track/clipitem")) == 1


def test_track_heights_are_saved_and_bounded():
    seq = sequence([])
    seq.tracks[1].height = 140
    saved = ed.save_sequence(seq)
    assert ed.read_sequence(saved["id"])["tracks"][1]["height"] == 140
    assert ed.read_sequence(saved["id"])["tracks"][0]["height"] is None
    raw = seq.model_dump()
    raw["tracks"][0]["height"] = 1000
    with pytest.raises(ValidationError):
        ed.Sequence.model_validate(raw)


def test_old_sequences_load_with_no_subclips_and_green_markers():
    raw = sequence([]).model_dump()
    raw.pop("subclips")
    raw["markers"] = [{"time": 1.0, "label": "Old"}]
    seq = ed.Sequence.model_validate(raw)
    assert seq.subclips == [] and seq.markers[0].color == "green"
    with pytest.raises(ValidationError):
        ed.Sequence.model_validate(raw | {"markers": [{"time": 1, "label": "x", "color": "url(evil)"}]})


def test_subclips_are_bounded_checked_against_the_bin_and_protect_media(tmp_path):
    tone = add(make(tmp_path / "tone.wav", "sine=f=300", seconds=2))
    sub = {"id": "s1", "media": tone["id"], "source_in": 0.5, "source_out": 1.5, "name": "Hook"}
    with pytest.raises(ValidationError, match="out point"):
        sequence([], subclips=[sub | {"source_out": 0.5}])
    with pytest.raises(ValidationError):
        sequence([], subclips=[sub | {"name": "x" * 61}])
    with pytest.raises(ValidationError, match="unique"):
        sequence([], subclips=[sub, sub])
    with pytest.raises(ed.EditorError, match="not in the bin"):
        ed.save_sequence(sequence([], subclips=[sub | {"media": "c" * 32}]))
    with pytest.raises(ed.EditorError, match="ends after"):
        ed.save_sequence(sequence([], subclips=[sub | {"source_out": 9}]))
    saved = ed.save_sequence(sequence([], subclips=[sub]))
    assert ed.read_sequence(saved["id"])["subclips"][0]["name"] == "Hook"
    with pytest.raises(ed.EditorError, match="Test cut"):
        ed.delete_media(tone["id"])


def cut_with_a_pause(path: Path) -> Path:
    """4 s: red then blue picture (cut at 2 s), a tone that stops between 1.0 and 2.5 s."""
    tone = "aevalsrc=exprs='if(between(t,1,2.5),0,0.5*sin(2*PI*440*t))':s=44100:d=4"
    graph = "[0:v][1:v]concat=n=2:v=1:a=0[v]"
    args = [FF, "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=160x90:r=25:d=2"]
    args += ["-f", "lavfi", "-i", "color=c=blue:s=160x90:r=25:d=2", "-f", "lavfi", "-i", tone]
    args += ["-filter_complex", graph, "-map", "[v]", "-map", "2:a", "-c:v", "libx264", "-pix_fmt", "yuv420p"]
    subprocess.run(args + ["-c:a", "aac", "-shortest", str(path)], check=True)
    return path


def test_silence_parser_keeps_a_pause_that_runs_to_the_end():
    lines = [
        "[Parsed_silencedetect_0 @ 0x6000] silence_start: -0.002\n",
        "[Parsed_silencedetect_0 @ 0x6000] silence_end: 1.5 | silence_duration: 1.5\n",
        "[Parsed_ebur128_1 @ 0x7000] t: 0.1 TARGET:-23 LUFS M: -12.5 S:-inf I: -70.0 LUFS\n",
        "[Parsed_silencedetect_0 @ 0x6000] silence_start: 8.25\n",
        "unrelated line silence_start: 3\n",
    ]
    assert ed.parse_silence(lines, 10.0) == [(0.0, 1.5), (8.25, 10.0)]
    assert ed.parse_loudness(lines) == [(0.1, -12.5)]
    shown = ["[Parsed_showinfo_2 @ 0x1] n:   0 pts:  50 pts_time:2.04 duration:1\n"]
    assert ed.parse_scenes(shown) == [2.04]


def test_silence_and_scene_cuts_are_found_in_real_media(tmp_path):
    media = add(cut_with_a_pause(tmp_path / "cut.mp4"))
    seen: list[float] = []
    (start, end), *rest = ed.detect_silence(media["id"], -50, 0.5, seen.append)
    assert not rest and start == pytest.approx(1.0, abs=0.1) and end == pytest.approx(2.5, abs=0.1)
    assert seen and all(0 <= f < 1 for f in seen)
    cuts = ed.detect_scenes(media["id"], 0.3)
    assert len(cuts) == 1 and cuts[0] == pytest.approx(2.0, abs=0.1)
    stopped = threading.Event()
    stopped.set()
    with pytest.raises(ed.Cancelled):
        ed.detect_silence(media["id"], -50, 0.5, cancel=stopped)


def test_moments_prefer_a_loud_window_without_pauses():
    duration = 120.0
    loud = [(t / 10, -14.0 if 60 <= t / 10 < 90 else -32.0) for t in range(1200)]
    pauses = [(float(s), s + 1.5) for s in range(5, 120, 6) if not 58 <= s < 92]
    moments = ed.score_moments(duration, loud, pauses, None, 15, 30, 3)
    best = moments[0]
    assert best["score"] == 100 and 58 <= best["start"] and best["end"] <= 92
    assert "loud" in best["reasons"] and "few pauses" in best["reasons"]
    assert all(m["score"] <= best["score"] for m in moments)
    spans = sorted((m["start"], m["end"]) for m in moments)
    assert all(a[1] <= b[0] for a, b in zip(spans, spans[1:])), "moments must not overlap"


def test_moments_snapped_to_pauses_keep_their_length_limits_and_never_overlap():
    loud = [(t / 10, -20.0 - (t % 7)) for t in range(100)]
    for lo, hi in ((1, 1), (1, 2), (2, 3)):
        moments = ed.score_moments(10, loud, [(0.5, 1.2), (1.3, 1.4), (4.2, 4.6), (7.1, 7.3)], None, lo, hi, 5)
        assert moments
        assert all(lo - 1e-6 <= m["end"] - m["start"] <= hi + 1e-6 for m in moments), (lo, hi, moments)
        spans = sorted((m["start"], m["end"]) for m in moments)
        assert all(a[1] <= b[0] for a, b in zip(spans, spans[1:])), (lo, hi, moments)


def test_analysis_results_are_cached_per_kind_and_settings(tmp_path, monkeypatch):
    media = add(cut_with_a_pause(tmp_path / "cut.mp4"))
    params = {"noise_db": -50.0, "min_seconds": 0.5}
    first = ed.analyse(media["id"], "silence", params)
    assert first["kind"] == "silence" and len(first["ranges"]) == 1
    monkeypatch.setattr(ed, "detect_silence", lambda *a, **k: pytest.fail("should reuse the cached result"))
    assert ed.analyse(media["id"], "silence", params) == first
    assert ed.analysis_key("silence", params) != ed.analysis_key("silence", params | {"min_seconds": 1.0})
    moments = ed.analyse(media["id"], "moments", {"min_length": 1, "max_length": 2, "count": 2})["moments"]
    assert 1 <= len(moments) <= 2 and all(0 <= m["score"] <= 100 for m in moments)


def test_analysis_will_not_follow_a_playlist_to_other_files(tmp_path, monkeypatch):
    make(tmp_path / "private.wav", "sine=f=440", seconds=1)
    disguised = tmp_path / "proxy.mp4"
    disguised.write_text("ffconcat version 1.0\nfile 'private.wav'\n")
    stream = ["-map", "0:a:0", "-af", "ebur128"]
    with pytest.raises(ed.EditorError):
        ed._analyse(disguised, stream, 1.0, ("ebur128",), lambda f: None, threading.Event())
    monkeypatch.setattr(ed, "INPUT_GUARD", [])
    assert ed._analyse(disguised, stream, 1.0, ("ebur128",), lambda f: None, threading.Event())


def poll(c: TestClient, url: str) -> dict:
    for _ in range(600):
        job = c.get(url).json()
        if job["status"] != "running":
            return job
        time.sleep(0.1)
    raise AssertionError(f"{url} never finished")


def test_api_analysis_jobs_run_cache_cancel_and_bound_settings(tmp_path):
    c = client()
    media = add(cut_with_a_pause(tmp_path / "cut.mp4"))
    url = f"/api/editor/media/{media['id']}/analysis"
    assert c.post(url, json={"kind": "silence", "noise_db": 5}).status_code == 422
    assert c.post(url, json={"kind": "moments", "min_length": 30, "max_length": 10}).status_code == 422
    assert c.post(url, json={"kind": "transcript"}).status_code == 422
    assert c.post(f"/api/editor/media/{'b' * 32}/analysis", json={"kind": "scenes"}).status_code == 404

    job = c.post(url, json={"kind": "silence", "noise_db": -50, "min_seconds": 0.5})
    assert job.status_code == 202 and "cancel" not in job.json()
    done = poll(c, f"{url}/{job.json()['id']}")
    assert done["status"] == "done" and done["kind"] == "silence" and len(done["result"]["ranges"]) == 1
    from naturalvoice import server

    assert server.processing.acquire(blocking=False), "the slot is free once the job reports done"
    server.processing.release()
    again = c.post(url, json={"kind": "silence", "noise_db": -50, "min_seconds": 0.5}).json()
    assert again["status"] == "done" and again["result"] == done["result"], "the cached result is reused at once"

    other = add(make(tmp_path / "other.mp4", "testsrc2=s=160x90:r=25", "sine=f=300", seconds=1))
    assert c.get(f"/api/editor/media/{other['id']}/analysis/{done['id']}").status_code == 404
    assert c.get(f"{url}/{'f' * 32}").status_code == 404

    with server.processing:  # busy with an export or upload
        busy = c.post(url, json={"kind": "scenes"})
    assert busy.status_code == 429

    scenes = c.post(url, json={"kind": "scenes", "threshold": 0.4}).json()
    c.post(f"{url}/{scenes['id']}/cancel")
    stopped = poll(c, f"{url}/{scenes['id']}")
    assert stopped["status"] in {"cancelled", "done"}
    assert server.processing.acquire(blocking=False), "the processing slot is released"
    server.processing.release()

    from naturalvoice import editor_api

    editor_api.analyses["r" * 32] = {"id": "r" * 32, "media": media["id"], "status": "running", "created": 0}
    try:
        assert c.delete(f"/api/editor/media/{media['id']}").status_code == 409, "not removed mid-analysis"
    finally:
        editor_api.analyses.pop("r" * 32)
    assert c.delete(f"/api/editor/media/{media['id']}").status_code == 204


def test_api_batch_exports_each_range_as_its_own_file(tmp_path):
    c = client()
    source = make(tmp_path / "talk.mp4", "testsrc2=s=320x180:r=25", "sine=f=300", seconds=3)
    media = add(source)
    body = sequence([clip("c1", "v1", media["id"], 0, 0, 3)]).model_dump()
    one = {"in": 0.5, "out": 1.5, "label": "Hook <1>/../x"}
    bad: list[dict[str, object]] = [
        {"ranges": []},
        {"ranges": [{"in": 1, "out": 1}]},
        {"ranges": [{"in": 0, "out": 1}] * 51},
        {"ranges": [one | {"label": "x" * 61}]},
    ]
    for extra in bad:
        assert c.post("/api/editor/exports", json={"sequence": body} | extra).status_code == 422, extra
    beyond = c.post("/api/editor/exports", json={"sequence": body, "ranges": [one, {"in": 5, "out": 6}]})
    assert beyond.status_code == 400 and beyond.json()["detail"].startswith("Range 2:")

    ranges = [one, {"in": 2, "out": 3}]
    job = c.post("/api/editor/exports", json={"sequence": body, "quality": "draft", "ranges": ranges}).json()
    assert job["files"] == ["Test cut-01-Hook 1..x.mp4", "Test cut-02.mp4"]
    status = poll(c, f"/api/editor/exports/{job['id']}")
    assert status["status"] == "done" and status["done"] == 2, status
    from naturalvoice import server

    # A finished job has already freed the slot, so the next one can start at once.
    assert server.processing.acquire(blocking=False), "the slot is free once the job reports done"
    server.processing.release()
    for index, name in enumerate(job["files"]):
        r = c.get(f"/api/editor/exports/{job['id']}/file?index={index}")
        assert r.content[4:8] == b"ftyp" and quote(name) in r.headers["content-disposition"]
        saved = tmp_path / f"part{index}.mp4"
        saved.write_bytes(r.content)
        assert ed.probe(saved)["duration"] == pytest.approx(1.0, abs=0.1)
    assert c.get(f"/api/editor/exports/{job['id']}/file?index=2").status_code == 404
    assert c.get(f"/api/editor/exports/{job['id']}/file?index=-1").status_code == 404


def test_captions_are_optional_bounded_and_track_checked():
    raw = sequence([]).model_dump()
    raw.pop("captions")
    assert ed.Sequence.model_validate(raw).captions is None
    seq = ed.Sequence.model_validate(raw | {"captions": {"track": "a1", "style": "karaoke"}})
    assert seq.captions and seq.captions.words_per_page == 3 and seq.captions.highlight == "#ffd400"
    saved = ed.save_sequence(seq)
    assert ed.read_sequence(saved["id"])["captions"]["style"] == "karaoke"
    for bad in (
        {"track": "zz"},
        {"size": 0.2},
        {"y": 0.05},
        {"words_per_page": 9},
        {"color": "red"},
        {"highlight": "#fff; x"},
        {"font": "../../etc/passwd"},
        {"style": "neon"},
    ):
        with pytest.raises(ValidationError):
            ed.Sequence.model_validate(raw | {"captions": bad})


def test_caption_strips_are_one_guarded_image_input_overlaid_last(tmp_path):
    red = add(make(tmp_path / "red.mp4", "color=c=red:s=320x180:r=25", "sine=f=300", seconds=2))
    seq = sequence([clip("c1", "v1", red["id"], 0, 0, 2)], captions={"y": 0.5})
    args, graph, _ = ed.build_command(seq, ed.media_for(seq), tmp_path / "o.mp4", captions_frames=tmp_path / "caps")
    patterns = [a for a in args if a.endswith("%07d.png")]
    assert patterns == [str(tmp_path / "caps" / "frames" / "%07d.png")]
    at = args.index(patterns[0])
    assert args[at - 3 : at] == ["-f", "image2", "-i"] and args[at - 3 - len(ed.INPUT_GUARD) : at - 3] == ed.INPUT_GUARD
    assert graph.count("[cap]overlay") == 1 and "overlay=x=0:y=72:" in graph
    assert graph.index("[cap]overlay") < graph.index("format=yuv420p[vout]")
    plain, plain_graph, _ = ed.build_command(seq, ed.media_for(seq), tmp_path / "o.mp4")
    assert not any(a.endswith(".png") for a in plain) and "[cap]" not in plain_graph


def test_burned_in_captions_appear_only_in_their_band_and_time(tmp_path):
    from naturalvoice import transcript as tr

    video = add(make(tmp_path / "talk.mp4", "testsrc2=s=320x180:r=25", "sine=f=300", seconds=4))
    tr.save_transcript(video["id"], [[1.0, 1.4, "Hello"], [1.4, 1.9, "world."]])
    clips = [clip("c1", "v1", video["id"], 0, 0, 4), clip("c2", "a1", video["id"], 0, 0, 4)]
    caps = {"style": "pop", "color": "#ffffff", "highlight": "#ffff00", "size": 0.1, "y": 0.5}
    out, plain = tmp_path / "captioned.mp4", tmp_path / "plain.mp4"
    ed.render(sequence(clips, captions=caps), out, False, "high", lambda f: None, threading.Event())
    ed.render(sequence(clips), plain, False, "high", lambda f: None, threading.Event())
    assert not any(p.name.endswith(".captions") for p in tmp_path.iterdir()), "caption strips are removed"

    def picture(video_path: Path, at: float) -> np.ndarray:
        raw = subprocess.run(
            [FF, "-v", "error", "-ss", str(at), "-i", str(video_path), "-frames:v", "1"]
            + ["-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            check=True,
            capture_output=True,
        ).stdout
        frame = np.frombuffer(raw, dtype=np.uint8).reshape(180, 320, 3).astype(float)
        return frame

    top, tall = 90 - 29, 58  # 18 px text, 58 px strip centred at half height
    during = np.abs(picture(out, 1.6) - picture(plain, 1.6)).mean(axis=(1, 2))
    assert during[top : top + tall].max() > 20, "caption pixels inside the band"
    assert during[: top - 2].max() < 3 and during[top + tall + 2 :].max() < 3, "nothing outside the band"
    after = np.abs(picture(out, 3.0) - picture(plain, 3.0)).mean(axis=(1, 2))
    assert after.max() < 3, "no caption once the page has ended"


def fake_speech_engine(tmp_path: Path, monkeypatch, body: str) -> None:
    import sys

    from naturalvoice import transcript as tr

    script = tmp_path / "fake_transcribe.py"
    script.write_text("import json, sys, time\nsys.stdin.readline()\n" + body, encoding="utf-8")
    monkeypatch.setattr(tr, "installed", lambda: True)
    monkeypatch.setattr(tr, "worker_command", lambda: [sys.executable, str(script)])


SPEECH = (
    "print(json.dumps({'progress': 1.0}), flush=True)\n"
    "print(json.dumps({'duration': 2, 'words': [[0.1, 0.3, 'Um,'], [0.3, 0.6, 'why'], [0.6, 0.9, 'captions?']]}))\n"
)


def test_api_transcripts_run_guard_edits_and_feed_hooks_and_srt(tmp_path, monkeypatch):
    from naturalvoice import editor_api, server
    from naturalvoice import transcript as tr

    c = client()
    media = add(make(tmp_path / "talk.mp4", "testsrc2=s=320x180:r=25", "sine=f=300", seconds=2))
    url = f"/api/editor/media/{media['id']}/transcript"
    monkeypatch.setattr(tr, "installed", lambda: False)
    status = c.get("/api/editor/transcribe/status").json()
    assert status["installed"] is False and "setup_speech_model.sh" in status["setup"]
    assert c.post(url, json={}).status_code == 503
    assert c.get(url).json() is None
    assert c.post(f"/api/editor/media/{media['id']}/hooks", json={}).status_code == 404

    fake_speech_engine(tmp_path, monkeypatch, SPEECH)
    with server.processing:
        assert c.post(url, json={}).status_code == 429
    job = c.post(url, json={})
    assert job.status_code == 202 and "cancel" not in job.json()
    done = poll(c, f"{url}/job/{job.json()['id']}")
    assert done["status"] == "done"
    data = c.get(url).json()
    assert [w[2] for w in data["words"]] == ["Um,", "why", "captions?"]
    assert data["fillers"] == [{"kind": "word", "index": 0}] and data["silence"] == tr.SILENCE_PARAMS

    assert c.put(url, json={"words": [[0.5, 0.2, "x"]]}).status_code == 400
    assert c.put(url, json={"words": "x"}).status_code == 422
    assert c.put(url, json={"words": [[0.1, 0.3, "Hey,"], [0.3, 0.6, "why"]]}).json()["edited"] is True
    assert c.post(url, json={}).status_code == 409, "edits are not replaced without confirmation"
    editor_api.transcriptions["t" * 32] = {"id": "t" * 32, "media": media["id"], "status": "running", "created": 0}
    try:
        assert c.put(url, json={"words": []}).status_code == 409
        assert c.delete(f"/api/editor/media/{media['id']}").status_code == 409
    finally:
        editor_api.transcriptions.pop("t" * 32)

    hooks = c.post(f"/api/editor/media/{media['id']}/hooks", json={"min_len": 5, "max_len": 60})
    assert hooks.status_code == 200 and hooks.json() == {"hooks": [], "ranked_by": "structure"}
    assert c.post(f"/api/editor/media/{media['id']}/hooks", json={"min_len": 60, "max_len": 10}).status_code == 422
    assert c.post(f"/api/editor/media/{media['id']}/hooks", json={"count": 21}).status_code == 422

    seq = sequence([clip("c1", "a1", media["id"], 1.0, 0, 2)], captions={}).model_dump()
    srt = c.post("/api/editor/sequences/captions.srt", json=seq)
    assert srt.status_code == 200 and srt.headers["x-content-type-options"] == "nosniff"
    assert srt.headers["content-type"].startswith("text/plain") and "attachment" in srt.headers["content-disposition"]
    assert srt.text == "1\n00:00:01,100 --> 00:00:01,900\nHey, why\n"
    empty = sequence([clip("c1", "v1", media["id"], 0, 0, 2)], captions={"track": "a2"}).model_dump()
    assert c.post("/api/editor/sequences/captions.srt", json=empty).status_code == 400
    gone = sequence([clip("c1", "a1", "f" * 32, 1.0, 0, 2)], captions={}).model_dump()
    assert c.post("/api/editor/sequences/captions.srt", json=gone).status_code == 400

    from naturalvoice import captions as cap

    monkeypatch.setattr(cap, "MAX_SECONDS", 1)
    refused = c.post("/api/editor/exports", json={"sequence": seq})
    assert refused.status_code == 400 and "30 minutes" in refused.json()["detail"]


def test_api_hooks_rank_with_ai_only_when_connected(tmp_path, monkeypatch):
    from naturalvoice import llm
    from naturalvoice import transcript as tr

    c = client()
    media = add(make(tmp_path / "long.wav", "sine=f=200", seconds=40))
    words = []
    for n in range(4):
        base = n * 9.0
        text = f"Why does number {n} matter to you? It changes how the whole story is told today."
        for i, token in enumerate(text.split()):
            words.append([round(base + i * 0.5, 3), round(base + i * 0.5 + 0.4, 3), token])
    tr.save_transcript(media["id"], words)
    url = f"/api/editor/media/{media['id']}/hooks"
    found = c.post(url, json={"min_len": 5, "max_len": 10, "count": 4}).json()
    assert found["ranked_by"] == "structure" and len(found["hooks"]) >= 2
    monkeypatch.setattr(llm, "config", lambda: None)
    assert c.post(url, json={"min_len": 5, "max_len": 10, "use_ai": True}).status_code == 400
    monkeypatch.setattr(llm, "config", lambda: {"label": "test model"})
    monkeypatch.setattr(llm, "chat", lambda *a, **k: "[1, 0]")
    ranked = c.post(url, json={"min_len": 5, "max_len": 10, "count": 4, "use_ai": True}).json()
    assert ranked["ranked_by"] == "ai" and [h["id"] for h in ranked["hooks"]][:2] == [1, 0]

    def offline(*a, **k):
        raise RuntimeError("Couldn't reach the model.")

    monkeypatch.setattr(llm, "chat", offline)
    failed = c.post(url, json={"min_len": 5, "max_len": 10, "use_ai": True})
    assert failed.status_code == 502 and failed.json()["detail"] == "Couldn't reach the model."


def test_api_caption_fonts_are_allowlisted():
    from naturalvoice import captions as cap

    c = client()
    for key in ("../../etc/passwd", "Arial Bold.ttf", "unknown"):
        assert c.get(f"/api/editor/caption-fonts/{key}").status_code == 404
    reply = c.get("/api/editor/caption-fonts/sans-bold")
    if cap.font_file("sans-bold") is None:
        assert reply.status_code == 404
    else:
        assert reply.status_code == 200 and reply.headers["content-type"] == "font/ttf"
        assert reply.content == cap.font_file("sans-bold").read_bytes()  # type: ignore[union-attr]
