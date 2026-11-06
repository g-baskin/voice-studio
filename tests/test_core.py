import subprocess
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from naturalvoice import bench, humanize as hz
from naturalvoice.audio import load

SR = 24000


def test_web_template_interactions():
    import json
    import shutil

    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for the UI interaction checks")
    subprocess.run(
        [
            node,
            "--experimental-strip-types",
            "--no-warnings",
            str(Path(__file__).with_name("web_templates.cjs")),
            json.dumps({k: s.to_dict() for k, s in hz.PRESETS.items()}),
        ],
        check=True,
    )


def test_studio_drafts_load_safely():
    """A Studio draft restored from a backup may be damaged; it must load as safe defaults."""
    import shutil

    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for the Studio draft checks")
    subprocess.run(
        [node, "--experimental-strip-types", "--no-warnings", str(Path(__file__).with_name("studio_drafts.cjs"))],
        check=True,
    )


def test_web_script_syntax():
    """A parse error disables every control, including file picking and dropping."""
    import shutil

    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for the browser JavaScript syntax check")
    frontend = Path(__file__).parents[1] / "frontend"
    modules = sorted((frontend / "src/lib/clean").glob("*.ts"))
    assert modules, "No Clean page modules found"
    for module in modules:
        subprocess.run(
            [
                node,
                "--experimental-strip-types",
                "--no-warnings",
                "--input-type=module",
                "-e",
                f"await import({module.as_uri()!r})",
            ],
            check=True,
        )
    if not (frontend / "node_modules/svelte").is_dir():
        pytest.skip("Frontend tools are not installed")
    page = frontend / "src/routes/+page.svelte"
    check = "require('svelte/compiler').compile(require('fs').readFileSync(process.argv[1], 'utf8'), {filename: 'page.svelte'})"
    subprocess.run([node, "-e", check, str(page)], cwd=frontend, check=True)


def speechlike(seconds=6.0, seed=0):
    """Voiced 'syllables' (jittery glottal pulse train through moving formants) with real pauses."""
    from scipy import signal

    rng = np.random.default_rng(seed)
    out = np.zeros(int(seconds * SR), dtype=np.float32)
    t = 0.2
    while t < seconds - 0.6:
        dur = rng.uniform(0.15, 0.35)
        n = int(dur * SR)
        f0 = rng.uniform(110, 210) * (1 + 0.05 * np.sin(np.linspace(0, 3, n)))
        phase = np.cumsum(f0 * (1 + rng.normal(0, 0.01, n)) / SR)
        src = (np.diff(np.floor(phase), prepend=0) > 0).astype(float)  # pulse train, all harmonics
        b, a = signal.butter(1, 800 / (SR / 2))
        src = signal.lfilter(b, a, src)  # natural spectral tilt
        y = 0.02 * rng.standard_normal(n)
        for fc, bw in ((rng.uniform(500, 800), 80), (rng.uniform(1100, 1800), 120), (2600, 200), (3500, 300)):
            b, a = signal.iirpeak(fc, fc / bw, fs=SR)
            y = y + signal.lfilter(b, a, src)
        env = np.sin(np.pi * np.arange(n) / n) ** 0.5
        s = int(t * SR)
        out[s : s + n] += (y * env).astype(np.float32)
        t += dur + (rng.uniform(0.25, 0.5) if rng.random() < 0.4 else rng.uniform(0.03, 0.08))
    return out / np.abs(out).max() * 0.6


def test_chain_shapes_and_levels():
    x = speechlike()
    for preset in hz.PRESETS:
        y = hz.humanize(x, SR, hz.get_settings(preset))
        assert y.shape == x.shape and y.dtype == np.float32
        assert np.isfinite(y).all() and np.abs(y).max() <= 0.9
    st = hz.humanize(np.stack([x, x * 0.9], 1), SR)
    assert st.shape == (len(x), 2)


def test_dereverb_removes_echo_tail():
    ref = speechlike(seed=1)
    wet = bench._reverb(ref, SR, 0.7, 0).astype(np.float32)
    before = bench.score(ref, wet, SR, full=False)["echo"]
    after = bench.score(ref, hz.dereverb(wet, SR, 0.8), SR, full=False)["echo"]
    assert after < before - 8, (before, after)


def test_dereverb_leaves_dry_voice_alone():
    ref = speechlike(seed=2)
    y = hz.dereverb(ref, SR, 1.0)
    assert np.allclose(y, ref, atol=1e-3)  # dry input is detected and left alone


def test_demetal_cuts_injected_resonance():
    # speech-shaped noise bursts: a fixed ringing filter shows up in every burst
    rng = np.random.default_rng(3)
    from scipy import signal as sg

    ref = sg.lfilter(*sg.butter(1, 1500 / (SR / 2)), rng.standard_normal(6 * SR)) * (speechlike(seed=3) != 0)
    ref = (ref / np.abs(ref).max() * 0.6).astype(np.float32)
    bad = bench._resonances(ref, SR, freqs=(3100,), gain_db=12).astype(np.float32)
    found = [f for f, *_ in hz.find_resonances(bad, SR)]
    assert any(abs(f - 3100) < 120 for f in found), found
    y = hz.demetal(bad, SR, 1.0)

    def level_at(sig, f0):
        from scipy import signal

        f, p = signal.welch(sig, SR, nperseg=2048)
        return 10 * np.log10(p[np.argmin(abs(f - f0))])

    assert level_at(y, 3100) < level_at(bad, 3100) - 4


def test_normalize_preserves_intelligibility():
    ref = speechlike(seed=4)
    assert bench.score(ref, hz.normalize(ref, SR, -16), SR, full=False)["STOI"] > 0.97


def test_bench_summary_render():
    rows = [
        {
            "damage": "small room echo",
            "voice": "v",
            "method": m,
            "rtf": 0.1,
            "OVRL": o,
            "SIG": 3,
            "BAK": 3,
            "PESQ": 1.2,
            "STOI": 0.8,
            "echo": -50,
            "metal": 2,
        }
        for m, o in (("untouched", 2.0), ("AI cleanup only", 2.5))
    ]
    r = bench.summarize(rows, ["untouched", "AI cleanup only"])
    assert r["overall"]["AI cleanup only"]["OVRL"] == 2.5
    md = bench.render(r)
    assert "(+0.50)" in md and "**2.5**" in md


MODELS = Path(__file__).parents[1] / "models"


@pytest.mark.skipif(not (MODELS / "dnsmos_sig_bak_ovr.onnx").exists(), reason="DNSMOS not downloaded")
def test_dnsmos_ranks_clean_above_echo():
    from naturalvoice import quality

    ref = speechlike(10.0, seed=5)
    wet = bench._reverb(ref, SR, 1.0, 4).astype(np.float32)
    clean, bad = quality.dnsmos(ref, SR), quality.dnsmos(wet, SR)
    assert all(1.0 <= v <= 5.0 for v in clean.values())
    assert clean["BAK"] > bad["BAK"]
    score = quality.pesq_wb(ref, ref, SR)
    assert score is not None and score > 4.4


def test_mel_matches_librosa_shape_and_range():
    from naturalvoice import quality

    m = quality.melspec_db(np.random.default_rng(0).standard_normal(144000).astype(np.float32))
    assert m.shape == (900, 120) and m.max() <= 1.0 + 1e-6 and m.min() >= -1.0 - 1e-6


REF = Path(__file__).parents[1] / "bench/refs/af_heart.wav"


@pytest.mark.skipif(
    not (MODELS / "gtcrn_simple.onnx").exists() or not REF.exists(),
    reason="GTCRN or reference voice missing (run `naturalvoice bench` once)",
)
def test_ai_clean_reduces_echo_and_keeps_length():
    from naturalvoice import enhance

    ref = load(REF)[0][:, 0]  # the AI model needs real speech, not the synthetic buzz above
    wet = bench._reverb(ref, SR, 0.8, 2).astype(np.float32)
    y = enhance.ai_clean(wet, SR, 1.0)
    assert y.shape == wet.shape and np.isfinite(y).all()
    assert bench.score(ref, y, SR, full=False)["echo"] < bench.score(ref, wet, SR, full=False)["echo"]
    assert np.allclose(enhance.ai_clean(wet, SR, 0.0), wet)


@pytest.fixture()
def client():
    from naturalvoice.server import app

    return TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000))


def _wait(client, job):
    for _ in range(200):
        j = client.get(f"/api/jobs/{job}").json()
        if j["status"] != "running":
            return j
        time.sleep(0.1)
    raise AssertionError("job did not finish")


def test_api_clean_audio(client, tmp_path):
    p = tmp_path / "in.wav"
    sf.write(p, bench._reverb(speechlike(), SR, 0.6, 0), SR)
    assert client.get("/").status_code == 200
    assert set(client.get("/api/presets").json()) == {"light", "standard", "strong"}
    job = client.post(
        "/api/clean", files={"file": ("in.wav", p.read_bytes(), "audio/wav")}, data={"preset": "standard"}
    ).json()["job"]
    j = _wait(client, job)
    assert j["status"] == "done", j
    r = client.get(f"/api/jobs/{job}/result")
    assert r.status_code == 200 and r.content[:4] == b"RIFF"
    assert j["result"]["after"]["seconds"] == j["result"]["before"]["seconds"]


def test_api_rejects_bad_preset(client):
    r = client.post("/api/clean", files={"file": ("a.wav", b"x", "audio/wav")}, data={"preset": "nope"})
    assert r.status_code == 400


def test_api_clean_video_keeps_picture(client, tmp_path):
    wav = tmp_path / "a.wav"
    sf.write(wav, speechlike(3.0), SR)
    mp4 = tmp_path / "in.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=green:s=160x120:d=3",
            "-i",
            str(wav),
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(mp4),
        ],
        check=True,
    )
    job = client.post("/api/clean", files={"file": ("in.mp4", mp4.read_bytes(), "video/mp4")}).json()["job"]
    j = _wait(client, job)
    assert j["status"] == "done", j
    out = tmp_path / "out.mp4"
    out.write_bytes(client.get(f"/api/jobs/{job}/result").content)
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(out)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert "video" in probe and "audio" in probe
    audio, sr = load(out)
    assert abs(len(audio) / sr - 3.0) < 0.2


def test_tts_split_keeps_punctuation():
    from naturalvoice.tts import split_chunks

    chunks = split_chunks("Hello there, friend. How are you?\n\nGreat!")
    assert chunks[0][0].startswith("Hello there")
    assert any(c.endswith("?") for c, _ in chunks)
    assert max(p for _, p in chunks) >= 0.6  # paragraph pause


@pytest.mark.skipif(
    not (Path(__file__).parents[1] / "models/kokoro-v1.0.onnx").exists(), reason="voice model not downloaded"
)
def test_tts_offline_speaks():
    from naturalvoice import tts

    a, sr = tts.speak("Hello there.", "af_heart")
    assert sr == 24000 and len(a) > sr * 0.5 and np.abs(a).max() > 0.05
