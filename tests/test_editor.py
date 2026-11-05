"""Editor: media preparation, sequence rules, timeline export and Premiere XML."""

from __future__ import annotations

import subprocess
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path

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
