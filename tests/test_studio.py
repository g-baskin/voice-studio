import io
import json
import time
import zipfile

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from naturalvoice import server, studio as st, studio_api, voices


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(voices, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(studio_api, "WORK", tmp_path / "work")
    monkeypatch.setattr(studio_api, "jobs", {})
    return TestClient(server.app)


# ---------------------------------------------------------------- parsing
def test_speaker_tags_and_cast():
    res = st.parse_script(
        "NARRATOR: Hello there.\n[Guest] Hi!\nAnd more from the guest.\n\nnarrator: Bye.", {"narrator": "bm_george"}
    )
    lines = res["lines"]
    assert [ln["speaker"] for ln in lines] == ["NARRATOR", "Guest", "Guest", "narrator"]
    assert lines[0]["voice"] == lines[3]["voice"] == "bm_george"
    assert lines[1]["voice"] != "bm_george" and lines[1]["voice"] == lines[2]["voice"]
    assert lines[2]["text"] == "And more from the guest."
    assert {c["speaker"] for c in res["cast"]} == {"NARRATOR", "Guest"}


def test_pause_tag_at_start_is_not_a_speaker():
    res = st.parse_script("[pause 1s] Welcome back.")
    assert res["lines"][0]["speaker"] == "" and res["lines"][0]["text"].startswith("[pause 1s]")


def test_pause_and_unknown_tags():
    segs, warn = st.parse_inline("One. [pause 1.5s] Two [break] three [whisper] four [pause 20s] five [pause 300ms]")
    pauses = [v for k, v in segs if k == "pause"]
    assert pauses == [1.5, st.BREAK_SECONDS, 10.0, 0.3]
    assert any("[whisper]" in w and "Unknown" in w for w in warn)
    assert any("outside" in w for w in warn)
    # unknown tag is kept as text, not eaten
    assert any("[whisper]" in str(v) for k, v in segs if k == "text")


def test_dictionary_whole_word_case_insensitive():
    marked, hits = st.mark_dictionary("Nginx and NGINX, not nginxy. GIF!", {"nginx": "engine x", "gif": "/ɡɪf/"})
    assert st.spoken_text(marked, hits) == "engine x and engine x, not nginxy. GIF!"
    assert st.display_text(marked, hits) == "Nginx and NGINX, not nginxy. GIF!"


# ---------------------------------------------------------------- captions
def test_captions_from_rendered_timings():
    phrases = [
        {"start": 0.5, "end": 1.4, "text": "Hello there,", "speaker": "A"},
        {"start": 1.6, "end": 2.5, "text": "friend.", "speaker": "A"},
        {"start": 3.0, "end": 12.0, "text": " ".join(["word"] * 40) + ".", "speaker": "B"},
    ]
    cues = st.caption_cues(phrases)
    assert cues[0] == {"start": 0.5, "end": 2.5, "text": "Hello there, friend.", "speaker": "A"}
    long = cues[1:]
    assert len(long) >= 2 and all(len(c["text"]) <= 84 for c in long)
    assert long[0]["start"] == 3.0 and abs(long[-1]["end"] - 12.0) < 1e-6
    srt = st.to_srt(cues)
    assert "1\n00:00:00,500 --> 00:00:02,500\nHello there, friend." in srt
    assert st.to_vtt(cues).startswith("WEBVTT\n\n1\n00:00:00.500 --> 00:00:02.500")
    assert all(len(r) <= 42 for c in long for r in st._wrap(c["text"]).split("\n"))


# ---------------------------------------------------------------- DSP
def test_ducking_lowers_music_under_speech():
    sr = 24000
    voice = np.zeros(sr * 6, np.float32)
    voice[2 * sr : 4 * sr] = 0.2 * np.sin(2 * np.pi * 200 * np.arange(2 * sr) / sr)
    g = st.duck_gain(voice, sr, depth_db=12)
    under = 20 * np.log10(g[int(2.8 * sr) : int(3.6 * sr)].mean())
    before = 20 * np.log10(g[int(0.5 * sr) : int(1.0 * sr)].mean())
    after = 20 * np.log10(g[int(5.5 * sr) :].mean())
    assert under < -10 and before > -0.5 and after > -1.5


def test_mastering_hits_targets_on_synthetic():
    sr = 24000
    rng = np.random.default_rng(0)
    x = (rng.standard_normal(sr * 8) * 0.05 * (np.sin(np.arange(sr * 8) / sr * 6) > 0)).astype(np.float32)
    for target in ("youtube", "podcast", "broadcast"):
        y, _, rep = st.master(x, sr, target)
        assert abs(rep["measured"]["lufs"] - st.TARGETS[target]["lufs"]) <= 1.0
        assert rep["measured"]["true_peak_db"] <= -1.0


# ---------------------------------------------------------------- real render (Kokoro)
def _project():
    return {
        "title": "Test",
        "dictionary": {"Kokoro": "koh koh roh"},
        "lines": [
            {"text": "Welcome to the show. [pause 0.5s] Kokoro speaks today.", "voice": "af_heart", "speaker": "Host"},
            {
                "text": "Thanks for having me.",
                "voice": "am_michael",
                "speaker": "Guest",
                "delivery": "warm",
                "pitch": 1,
            },
            {"text": "Let's begin.", "voice": "af_heart", "speaker": "Host", "delivery": "energetic"},
        ],
    }


def _wait(c, job, timeout=300):
    t = time.time()
    while time.time() - t < timeout:
        s = c.get(f"/api/studio/render/{job}").json()
        if s["status"] != "running":
            return s
        time.sleep(0.3)
    raise AssertionError("render timed out")


def test_render_via_api_loudness_stems_captions(client, tmp_path):
    music = io.BytesIO()
    sr = 24000
    sf.write(music, (0.3 * np.sin(2 * np.pi * 330 * np.arange(sr * 3) / sr)).astype(np.float32), sr, format="WAV")
    mid = client.post("/api/studio/music", files={"file": ("bed.wav", music.getvalue(), "audio/wav")}).json()[
        "music_id"
    ]
    r = client.post(
        "/api/studio/render",
        json={"project": _project(), "target": "podcast", "stems": True, "music_id": mid, "music_level_db": -30},
    )
    assert r.status_code == 200, r.text
    s = _wait(client, r.json()["job"])
    assert s["status"] == "done", s
    res = s["result"]
    assert not res["errors"]
    m = res["loudness"]["measured"]
    assert abs(m["lufs"] + 16) <= 1.0 and m["true_peak_db"] <= -1.0
    job = r.json()["job"]
    stems = [f["name"] for f in res["files"] if f["kind"] == "stem"]
    assert len(stems) == 3  # Host, Guest, music
    mix = next(f["name"] for f in res["files"] if f["kind"] == "mix")
    n = sf.info(io.BytesIO(client.get(f"/api/studio/render/{job}/file/{mix}").content)).frames
    for name in stems:
        assert sf.info(io.BytesIO(client.get(f"/api/studio/render/{job}/file/{name}").content)).frames == n
    srt = client.get(f"/api/studio/render/{job}/file/Test.srt").text
    assert "Kokoro speaks today." in srt and "koh koh" not in srt
    tl = json.loads(client.get(f"/api/studio/render/{job}/file/Test-timeline.json").text)
    assert [ln["speaker"] for ln in tl["lines"]] == ["Host", "Guest", "Host"]
    assert tl["lines"][0]["end"] < tl["lines"][1]["start"]
    # caption cues line up with rendered phrases
    assert tl["captions"][0]["start"] == tl["lines"][0]["phrases"][0]["start"]
    z = zipfile.ZipFile(io.BytesIO(client.get(f"/api/studio/render/{job}/file/{res['zip']}").content))
    assert {mix, "Test.srt", "Test.vtt", "Test-timeline.json"} <= set(z.namelist())
    assert client.get(f"/api/studio/render/{job}/file/..%2Fx").status_code == 404
    assert str(tmp_path) not in json.dumps(s)


def test_bad_line_does_not_kill_render(client):
    proj = _project()
    proj["lines"][1]["voice"] = "custom:0123456789ab"  # missing library voice
    s = _wait(client, client.post("/api/studio/render", json={"project": proj, "target": "raw"}).json()["job"])
    assert s["status"] == "done" and s["result"]["errors"][0]["line"] == 2
    s = _wait(client, client.post("/api/studio/render", json={"project": proj, "stop_on_error": True}).json()["job"])
    assert s["status"] == "error" and "Line 2" in s["error"]


def test_preview_cached(client):
    line = {"text": "Quick preview.", "voice": "af_heart"}
    a = client.post("/api/studio/preview", json={"line": line})
    assert a.status_code == 200 and a.headers["x-cache"] == "miss"
    b = client.post("/api/studio/preview", json={"line": line})
    assert b.headers["x-cache"] == "hit" and a.content == b.content


# ---------------------------------------------------------------- validation & projects
def test_validation(client):
    bad = [
        {"lines": [{"text": "x", "voice": "../etc"}]},
        {"lines": [{"text": "x", "speed": 5}]},
        {"lines": [{"text": "x", "pitch": "NaN"}]},
        {"lines": [{"text": "x"}] * 501},
        {"lines": [{"text": "x" * 5000}] * 11},
        {"dictionary": {"bad[": "x"}},
    ]
    for proj in bad:
        assert client.post("/api/studio/render", json={"project": proj}).status_code == 422
    assert client.post("/api/studio/render", json={"project": {"lines": []}}).status_code == 400
    assert client.get("/api/studio/projects/..%2F..").status_code in (400, 404)
    r = client.post("/api/studio/music", files={"file": ("x.exe", b"MZ", "application/octet-stream")})
    assert r.status_code == 400


def test_projects_crud(client, tmp_path):
    rec = client.post("/api/studio/projects", json=_project()).json()
    pid = rec["id"]
    assert (tmp_path / "data" / "projects" / f"{pid}.json").exists()
    got = client.get(f"/api/studio/projects/{pid}").json()
    assert got["project"]["lines"][1]["delivery"] == "warm"
    p = got["project"]
    p["title"] = "<b>Renamed</b>"
    assert client.put(f"/api/studio/projects/{pid}", json=p).status_code == 200
    dup = client.post(f"/api/studio/projects/{pid}/duplicate").json()
    titles = {x["title"] for x in client.get("/api/studio/projects").json()["projects"]}
    assert titles == {"<b>Renamed</b>", "<b>Renamed</b> (copy)"}
    (tmp_path / "data" / "projects" / f"{dup['id']}.json").write_text('{"project": {"lines": [{"speed": 99}]}}')
    assert client.get(f"/api/studio/projects/{dup['id']}").status_code == 422
    assert client.delete(f"/api/studio/projects/{pid}").status_code == 200
    assert client.get(f"/api/studio/projects/{pid}").status_code == 404


def test_429_when_busy(client):
    assert server.processing.acquire(blocking=False)
    try:
        r = client.post("/api/studio/render", json={"project": _project()})
        assert r.status_code == 429
        r = client.post("/api/studio/preview", json={"line": {"text": "Never cached line 429.", "voice": "af_heart"}})
        assert r.status_code == 429
    finally:
        server.processing.release()


# ---------------------------------------------------------------- fit to time, takes, ACX room tone
def _lines2():
    return [
        st.new_line("Fresh coffee, every morning.", "af_heart", "A"),
        st.new_line("Visit us today.", "am_michael", "B"),
    ]


def test_fit_to_time(tmp_path):
    proj = {"title": "fit", "lines": _lines2(), "dictionary": {}}
    base = st.render_project(proj, st.RenderOptions(target="raw", captions=False), tmp_path / "a")
    goal = round(base["duration"] * 0.92, 2)  # ~8% shorter: speed + stretch
    r = st.render_project(proj, st.RenderOptions(target="raw", captions=False, target_duration=goal), tmp_path / "b")
    assert r["fit"]["met"] and abs(r["duration"] - goal) <= 0.1, r["fit"]
    assert 0.85 <= r["fit"]["speed_factor"] <= 1.2 and not r["fit"]["warnings"]
    r = st.render_project(proj, st.RenderOptions(target="raw", captions=False, target_duration=1.0), tmp_path / "c")
    assert not r["fit"]["met"] and r["fit"]["warnings"] and r["fit"]["speed_factor"] == 1.2
    ln = {**_lines2()[0], "target": 1.6}
    a, ph, info = st.fit_line(ln, 1.6, {}, False)
    assert abs(len(a) / st.SR - 1.6) < 0.1 or info["warning"]
    assert ph[-1]["end"] <= len(a) / st.SR + 1e-6


def test_takes_differ_and_chosen_take_is_used(tmp_path):
    ln = _lines2()[1]
    a0, _ = st.render_line(ln, {}, False)
    a1, _ = st.render_line({**ln, "take": 4242}, {}, False)
    n = min(len(a0), len(a1))
    assert len(a0) != len(a1) or not np.allclose(a0[:n], a1[:n])
    assert st.line_key(ln, {}, False) != st.line_key({**ln, "take": 4242}, {}, False)
    proj = {"title": "t", "dictionary": {}, "lines": [{**ln, "take": 4242, "takes": [0, 4242]}]}
    r = st.render_project(proj, st.RenderOptions(target="raw", captions=False, line_clips=True, lead_in=0.0), tmp_path)
    clip = next(f["name"] for f in r["files"] if f["kind"] == "line")
    y, _ = sf.read(tmp_path / clip)
    assert len(y) == len(a1)


def test_acx_room_tone_noise_floor(tmp_path):
    proj = {"title": "acx", "dictionary": {}, "lines": _lines2()}
    r = st.render_project(proj, st.RenderOptions(target="acx", captions=False, sample_rate=44100), tmp_path)
    m = r["loudness"]["measured"]
    assert -75 < m["noise_floor_db"] <= -60, m
    assert -23 <= m["rms_db"] <= -18 and m["true_peak_db"] <= -3.0
    r = st.render_project(proj, st.RenderOptions(target="acx", captions=False, room_tone=False), tmp_path / "x")
    assert r["loudness"]["measured"]["noise_floor_db"] < -150


# ---------------------------------------------------------------- subtitles, timed placement, video dub
SRT = """1
00:00:00,500 --> 00:00:02,000
<i>Hello there.</i>

2
00:00:02,500 --> 00:00:04,000
HOST: Welcome back.

garbage block

3
00:00:05,000 --> 00:00:04,000
Backwards.
"""
VTT = """WEBVTT

NOTE a comment

00:01.000 --> 00:02.500 align:start
<v Ann>Hi, I'm Ann.

00:00:03.000 --> 00:00:04.200
Second cue.
"""


def test_parse_srt_vtt_and_bad_input():
    r = st.parse_subtitles(SRT)
    assert [(ln["start"], ln["end"], ln["text"]) for ln in r["lines"]] == [
        (0.5, 2.0, "Hello there."),
        (2.5, 4.0, "Welcome back."),
    ]
    assert r["lines"][1]["speaker"] == "HOST"
    assert any("no timing" in w for w in r["warnings"]) and any("before it starts" in w for w in r["warnings"])
    v = st.parse_subtitles(VTT)["lines"]
    assert v[0]["start"] == 1.0 and v[0]["speaker"] == "Ann" and v[0]["text"] == "Hi, I'm Ann."
    assert v[1]["end"] == 4.2
    for bad in ("", "just some text", "1\n00:00:aa,000 --> 00:00:01,000\nx"):
        with pytest.raises(st.StudioError):
            st.parse_subtitles(bad)


def test_subtitle_upload_api(client):
    r = client.post("/api/studio/subtitles", files={"file": ("a.vtt", VTT.encode(), "text/vtt")})
    assert r.status_code == 200 and len(r.json()["lines"]) == 2
    assert client.post("/api/studio/subtitles", files={"file": ("a.txt", b"x", "text/plain")}).status_code == 400
    big = b"1\n00:00:00,000 --> 00:00:01,000\n" + b"x" * (2 * 1024 * 1024)
    assert client.post("/api/studio/subtitles", files={"file": ("a.srt", big, "text/plain")}).status_code == 413


def _timed_project():
    a, b = (
        st.new_line("Good morning.", "af_heart", "A"),
        st.new_line("This line is far too long for its tiny slot, it will overrun.", "am_michael", "B"),
    )
    c = st.new_line("Bye.", "af_heart", "A")
    a.update(start=0.5, end=2.0)
    b.update(start=2.5, end=3.5)
    c.update(start=4.0, end=5.5)
    return {"title": "timed", "mode": "timed", "dictionary": {}, "lines": [a, b, c]}


def test_timed_placement_and_overruns(tmp_path):
    r = st.render_project(_timed_project(), st.RenderOptions(target="raw"), tmp_path)
    starts = [ln["start"] for ln in r["lines"]]
    assert all(abs(s - e) <= 0.01 for s, e in zip(starts, [0.5, 2.5, 4.0]))
    assert r["lines"][0]["end"] <= 2.0 + 0.05  # fits its slot
    assert any(o["line"] == 2 and o["kind"] == "overlap" for o in r["overlaps"])  # reported, not cut
    lf = next(x for x in r["line_fits"] if x["line"] == 2)
    assert lf["speed_factor"] <= 1.2 and lf["warning"]
    assert abs(r["captions"][0]["start"] - 0.5) < 0.05  # captions follow placed audio
    tl = json.loads((tmp_path / "timed-timeline.json").read_text())
    assert tl["mode"] == "timed"


def _tiny_video(path, seconds=6, audio=True):
    import subprocess
    from naturalvoice import audio as aio

    cmd = [aio._ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c=green:s=64x64:d={seconds}:r=10"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=300:duration={seconds}"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p"] + (["-c:a", "aac"] if audio else []) + ["-shortest", str(path)]
    subprocess.run(cmd, check=True)
    return path


def test_video_dub_mux(client, tmp_path):
    vid = _tiny_video(tmp_path / "in.mp4")
    up = client.post("/api/studio/video", files={"file": ("clip.mp4", vid.read_bytes(), "video/mp4")})
    assert up.status_code == 200, up.text
    assert up.json()["has_audio"] and abs(up.json()["seconds"] - 6) < 0.2
    proj = _timed_project()
    proj["lines"] = proj["lines"][:1]
    r = client.post(
        "/api/studio/render",
        json={
            "project": proj,
            "target": "podcast",
            "video_id": up.json()["video_id"],
            "video_mode": "duck",
            "sample_rate": 48000,
        },
    )
    s = _wait(client, r.json()["job"])
    assert s["status"] == "done", s
    name = next(f["name"] for f in s["result"]["files"] if f["kind"] == "video")
    data = client.get(f"/api/studio/render/{r.json()['job']}/file/{name}").content
    out = tmp_path / "out.mp4"
    out.write_bytes(data)
    streams = st.probe_streams(out)
    assert streams["video"] and streams["audio"]
    import subprocess
    from naturalvoice import audio as aio

    info = subprocess.run([aio._ffmpeg(), "-hide_banner", "-i", str(out)], capture_output=True, text=True).stderr
    assert "mov_text" in info and "h264" in info
    a, _ = aio.load(out)
    assert abs(len(a) / 48000 - 6.0) < 0.15
    assert abs(s["result"]["duration"] - 6.0) < 0.05
    assert str(tmp_path) not in json.dumps(s)
    bad = client.post("/api/studio/video", files={"file": ("x.mp4", b"not a video", "video/mp4")})
    assert bad.status_code == 400
    assert client.post("/api/studio/video", files={"file": ("x.avi", b"x", "video/x")}).status_code == 400


# ---------------------------------------------------------------- CLI
def test_cli_render(tmp_path, capsys):
    from naturalvoice import cli

    p = tmp_path / "proj.json"
    p.write_text(
        json.dumps(
            {
                "id": "x",
                "project": {
                    "title": "Cli",
                    "lines": [
                        {"text": "Hello.", "voice": "af_heart", "speaker": "A"},
                        {"text": "Hi.", "voice": "am_michael", "speaker": "B"},
                    ],
                },
            }
        )
    )
    rc = cli.main(["render", str(p), "-o", str(tmp_path / "out"), "--target", "broadcast", "--stems"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["target_met"] and abs(out["lufs"] + 23) <= 1 and out["true_peak_db"] <= -1
    assert "Cli-stem-A.wav" in out["files"] and (tmp_path / "out" / "Cli-mix.wav").exists()
    p.write_text(json.dumps({"lines": [{"text": "x", "speed": 9}]}))
    assert cli.main(["render", str(p)]) == 2
    assert "speed" in capsys.readouterr().err


def test_cli_dub(tmp_path, capsys):
    from naturalvoice import cli

    s = tmp_path / "cues.srt"
    s.write_text("1\n00:00:00,500 --> 00:00:01,800\nHello there.\n\n2\n00:00:02,000 --> 00:00:03,000\nBye.\n")
    vid = _tiny_video(tmp_path / "v.mp4", seconds=4)
    rc = cli.main(
        ["dub", str(s), "--voice", "bf_emma", "--video", str(vid), "--video-audio", "duck", "-o", str(tmp_path / "d")]
    )
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and "cues-dub.mp4" in out["files"] and abs(out["duration"] - 4) < 0.05
    assert st.probe_streams(tmp_path / "d" / "cues-dub.mp4")["video"]
    assert cli.main(["dub", str(s), "--voice", "../bad"]) == 2


# ---------------------------------------------------------------- custom styles & director's notes
def _ln(**kw):
    return {**st.new_line("Hello there.", "af_heart"), **kw}


def test_note_parser_speed_pitch_volume_pause():
    r = st.parse_note("slower, deeper and louder, dramatic pause", _ln())
    assert r["speed"] == 0.92 and r["pitch"] == -1.0 and r["volume"] == 3.0 and r["pause"] == 1.5
    assert len(r["understood"]) == 4 and r["unused"] == []
    r = st.parse_note("slightly faster, softly", _ln(speed=1.0, volume=-2))
    assert r["speed"] == 1.04 and r["volume"] == -3.5
    r = st.parse_note("rushed, quick pause", _ln())
    assert r["speed"] > 1.1 and r["pause"] == 0.15
    r = st.parse_note("whisper-soft, higher", _ln())
    assert r["volume"] == -6.0 and r["pitch"] == 1.0
    r = st.parse_note("purple flamingo energy", _ln())
    assert r["unused"] == ["purple", "flamingo", "energy"] and r["speed"] == 1.0


def test_note_parser_emotions_stock_vs_clone():
    r = st.parse_note("warm, slightly amused, slow down at the end", _ln())
    assert r["delivery"] == "warm" and r["tags"] == [] and r["text"] == "Hello there."
    assert any("slower" in u for u in r["understood"]) and any("ignored" in u for u in r["understood"])
    r = st.parse_note("tired", _ln())
    assert r["delivery"] == "soft" and r["speed"] == 0.95 and r["pitch"] == -0.5
    c = _ln(voice="clone:0123456789ab")
    r = st.parse_note("funny and surprised, laughing", c, ["chuckle", "laugh", "gasp"])
    assert r["tags"] == ["laugh", "chuckle", "gasp"] and r["text"].startswith("[laugh] [chuckle] [gasp] Hello")
    assert r["delivery"] == "neutral"
    r = st.parse_note("sigh", c, [])
    assert r["tags"] == [] and "doesn't offer" in r["understood"][0]
    r = st.parse_note("amused", {**c, "text": "[chuckle] Hi."}, ["chuckle"])
    assert r["text"] == "[chuckle] Hi."  # no duplicate tag


def test_clone_tags_pass_through_without_warning():
    segs, warn = st.parse_inline("Well [chuckle] okay.", frozenset({"chuckle"}))
    assert warn == [] and "".join(segment[1] for segment in segs if segment[0] == "text") == "Well [chuckle] okay."
    _, warn = st.parse_inline("Well [chuckle] okay.")
    assert warn  # stock voices: still warned


def test_style_capture_and_render_by_value():
    ln = _ln(delivery="warm", speed=1.1, volume=-2, pause=0.7)
    s_ = st.style_from_line(ln, "My warm")
    assert s_["speed"] == round(1.1 * 0.95, 3) and s_["pitch"] == -0.5 and s_["gain"] == -2.0
    assert s_["pause_after"] == 0.7 and s_["eq"][0][0] == "lowshelf"
    custom = _ln(delivery="custom", style=s_)
    assert st.delivery_of(custom)["speed"] == s_["speed"]
    assert st.line_key(custom, {}, False) != st.line_key({**custom, "style": {**s_, "pitch": 1}}, {}, False)
    with pytest.raises(st.StudioError):
        st.validate_style({"name": "x", "speed": float("nan")})
    with pytest.raises(st.StudioError):
        st.validate_style({"name": "x", "eq": [["notch", 100, 3]]})


def test_styles_api(client, tmp_path):
    assert client.get("/api/studio/styles").json()["styles"] == []
    r = client.post("/api/studio/styles", json={"name": "<b>Promo</b>", "line": _ln(delivery="energetic")})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    assert (tmp_path / "data" / "styles.json").exists()
    styles = client.get("/api/studio/styles").json()["styles"]
    assert styles[0]["name"] == "<b>Promo</b>" and styles[0]["speed"] == 1.1
    assert client.post("/api/studio/styles", json={"name": "x", "style": {"speed": 9}}).status_code == 400
    assert client.post("/api/studio/styles", json={"name": ""}).status_code == 422
    # a project keeps the style by value: still valid after the style is deleted
    proj = {"title": "s", "lines": [{**_ln(), "delivery": "custom", "style": styles[0]}]}
    assert client.delete(f"/api/studio/styles/{sid}").status_code == 200
    assert client.get("/api/studio/styles").json()["styles"] == []
    rec = client.post("/api/studio/projects", json=proj).json()
    got = client.get(f"/api/studio/projects/{rec['id']}").json()["project"]["lines"][0]
    assert got["delivery"] == "custom" and got["style"]["name"] == "<b>Promo</b>"
    assert client.delete("/api/studio/styles/NOT-HEX").status_code == 400
    (tmp_path / "data" / "styles.json").write_text("not json")
    assert client.get("/api/studio/styles").json()["styles"] == []
    n = client.post("/api/studio/note", json={"note": "slower", "line": _ln()}).json()
    assert n["speed"] == 0.92 and n["understood"] == ["slower"]
