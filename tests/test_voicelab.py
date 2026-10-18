import io
import time

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from naturalvoice import server, voicelab as vl, voicelab_api, voices as vlib

SHORT = "The bells rang out across the water."


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(vlib, "DATA_DIR", tmp_path)
    monkeypatch.setattr(vlib, "VOICE_DIR", tmp_path / "voices")
    monkeypatch.setattr(voicelab_api, "WORK", tmp_path / "work")
    monkeypatch.setattr(voicelab_api, "match_jobs", {})
    monkeypatch.setattr(vl, "MEASURE_LINE", SHORT)  # keep renders short in tests
    return TestClient(server.app)


def recipe(*pairs, **controls):
    return {"voices": [{"id": i, "weight": w} for i, w in pairs], "controls": controls}


def test_blend_normalises_and_is_weighted_mean():
    a, b = np.zeros(vlib.STYLE_SHAPE, np.float32), np.ones(vlib.STYLE_SHAPE, np.float32)
    out = vl.blend([a, b], [1, 3])
    assert out.shape == vlib.STYLE_SHAPE and np.allclose(out, 0.75)
    assert np.allclose(vl.normalise_weights([2, 2, 4]), [0.25, 0.25, 0.5])
    for bad in ([0, 0], [1, float("nan")], [-1, 2], [1, float("inf")]):
        with pytest.raises(ValueError):
            vl.normalise_weights(bad)


def test_recipe_validation():
    r = vl.validate_recipe(recipe(("af_heart", 1), ("am_michael", 3), gender=0.5))
    assert [v["weight"] for v in r["voices"]] == [0.25, 0.75]
    style, lang = vl.build_style(r)
    assert style.shape == vlib.STYLE_SHAPE and lang == "en-us"
    for bad in (
        recipe(("af_heart", 1)),
        recipe(*[(n, 1) for n in ["af_heart", "af_bella", "af_nicole", "am_adam", "am_michael", "bf_emma"]]),
        recipe(("af_heart", 1), ("nope", 1)),
        recipe(("af_heart", 1), ("af_heart", 1)),
        recipe(("af_heart", 1), ("am_adam", 1), gender=3),
        recipe(("af_heart", 1), ("am_adam", 1), pitch=1),
    ):
        with pytest.raises(ValueError):
            vl.validate_recipe(bad)


def test_gender_axis_moves_pitch():
    s = vlib.style_of("am_michael")
    ax = vl._axes()["gender"]
    low, high = (vl.pitch_hz(vl.render(s + g * 0.5 * ax, "en-us", SHORT)) for g in (-1, 1))
    assert high > low * 1.2


def test_design_save_rename_delete_via_api(client):
    lib = client.get("/api/voicelab/library", params={"kind": "stock", "gender": "female"}).json()
    assert lib["voices"] and all(v["gender"] == "female" for v in lib["voices"])
    r = recipe(("af_heart", 2), ("bf_emma", 1), gender=-0.3)
    wav = client.post("/api/voicelab/design/preview", json={"recipe": r, "text": "Hello there."})
    assert wav.status_code == 200 and wav.headers["content-type"] == "audio/wav"
    rec = client.post("/api/voicelab/design/save", json={"recipe": r, "name": "Warm Mix"}).json()
    vid = rec["id"]
    assert vid.startswith("custom:") and rec["meta"]["recipe"]["voices"][0]["weight"] == pytest.approx(2 / 3, abs=1e-3)
    custom = client.get("/api/voicelab/library", params={"kind": "custom"}).json()["voices"]
    assert [v["name"] for v in custom] == ["Warm Mix"] and custom[0]["editable"]
    t = time.time()
    assert client.get("/api/voicelab/preview", params={"voice": vid}).status_code == 200
    assert list((vlib.DATA_DIR / "previews").glob("*.wav"))
    t = time.time()
    assert client.get("/api/voicelab/preview", params={"voice": vid}).status_code == 200
    assert time.time() - t < 0.5  # cached
    # a custom voice can be blended again
    r2 = recipe((vid, 1), ("am_adam", 1))
    assert client.post("/api/voicelab/design/save", json={"recipe": r2, "name": "Second"}).status_code == 200
    assert client.post(f"/api/voicelab/voices/{vid}/rename", json={"name": "Renamed"}).json()["name"] == "Renamed"
    assert client.delete(f"/api/voicelab/voices/{vid}").status_code == 200
    assert client.get(f"/api/voicelab/voices/{vid}").status_code == 404
    assert client.delete("/api/voicelab/voices/af_heart").status_code == 400


def test_api_validation_errors_hide_paths(client, tmp_path):
    bad = [
        client.post("/api/voicelab/design/preview", json={"recipe": recipe(("af_heart", 1))}),
        client.post("/api/voicelab/design/preview", json={"recipe": recipe(("af_heart", 1), ("x", 1))}),
        client.post(
            "/api/voicelab/design/preview", json={"recipe": recipe(("af_heart", 1), ("am_adam", 1)), "text": "x" * 400}
        ),
        client.post("/api/voicelab/design/save", json={"recipe": recipe(("af_heart", 1), ("am_adam", 1)), "name": " "}),
        client.post("/api/voicelab/describe", json={"prompt": "x" * 400}),
        client.post("/api/voicelab/describe", json={"gender": "robot"}),
        client.get("/api/voicelab/preview", params={"voice": "custom:000000000000"}),
        client.post("/api/voicelab/voices/custom:../../etc/rename", json={"name": "x"}),
    ]
    for r in bad:
        assert 400 <= r.status_code < 500, r.text
        assert str(tmp_path) not in r.text and "/Users" not in r.text
    wav = io.BytesIO()
    sf.write(wav, np.zeros(24000 * 12, np.float32), 24000, format="WAV")
    no_consent = client.post("/api/voicelab/match", files={"file": ("a.wav", wav.getvalue())}, data={"budget": "5"})
    assert no_consent.status_code == 400 and "permission" in no_consent.text
    wrong_type = client.post("/api/voicelab/match", files={"file": ("a.exe", b"xx")}, data={"consent": "true"})
    assert wrong_type.status_code == 400
    short = io.BytesIO()
    sf.write(short, np.zeros(24000 * 2, np.float32), 24000, format="WAV")
    assert (
        client.post(
            "/api/voicelab/match", files={"file": ("a.wav", short.getvalue())}, data={"consent": "true", "budget": "5"}
        ).status_code
        == 400
    )


def test_busy_returns_429(client):
    assert server.processing.acquire(blocking=False)
    try:
        r = client.post("/api/voicelab/design/preview", json={"recipe": recipe(("af_heart", 1), ("am_adam", 1))})
        assert r.status_code == 429
    finally:
        server.processing.release()


def test_describe_maps_keywords_to_matching_stock_voices():
    out = vl.describe("warm, deep male narrator, British", seed=1)
    assert len(out["options"]) == 3 and "male" in out["understood"] and "British English" in out["understood"]
    for o in out["options"]:
        ids = [v["id"] for v in o["recipe"]["voices"]]
        assert all(i.startswith("bm_") for i in ids)
        assert o["recipe"]["controls"]["gender"] < 0
    assert len({str(o["recipe"]) for o in out["options"]}) == 3
    fem = vl.describe("", gender="female", accent="a", seed=2)
    assert all(v["id"].startswith("af_") for o in fem["options"] for v in o["recipe"]["voices"])


def test_match_job_end_to_end(client, monkeypatch):
    real = vl.match

    def match_candidates(ref, ref_sr, budget_s=180, progress=None, cancel=None):
        return real(
            ref,
            ref_sr,
            budget_s=budget_s,
            progress=progress,
            cancel=cancel,
            candidates=["af_heart", "am_michael", "bf_emma"],
        )

    monkeypatch.setattr(vl, "match", match_candidates)
    ref = vl.render(vlib.style_of("af_bella"), "en-us", "Every summer we picked tomatoes and carried them home.")
    ref = np.tile(np.concatenate([ref, np.zeros(4800, np.float32)]), 4)
    buf = io.BytesIO()
    sf.write(buf, ref, vl.SR, format="WAV")
    job = client.post(
        "/api/voicelab/match", files={"file": ("ref.wav", buf.getvalue())}, data={"consent": "true", "budget": "5"}
    ).json()["job"]
    for _ in range(240):
        st = client.get(f"/api/voicelab/match/{job}").json()
        if st["status"] != "running":
            break
        time.sleep(0.5)
    assert st["status"] == "done", st
    res = st["result"]
    assert -1 <= res["before"] <= res["after"] <= 1 and res["best_stock"][0]["id"] in {
        "af_heart",
        "am_michael",
        "bf_emma",
    }
    assert res["best_stock"][0]["id"] != "am_michael"  # a female reference should not match the male voice best
    assert client.get(f"/api/voicelab/match/{job}/audio", params={"which": "after"}).status_code == 200
    saved = client.post(f"/api/voicelab/match/{job}/save", json={"name": "Matched"}).json()
    assert saved["meta"]["source"] == "match" and saved["meta"]["similarity_after"] == res["after"]
    assert server.processing.acquire(blocking=False)
    server.processing.release()


def test_star_voices_end_to_end(client, tmp_path):
    """Stars persist on disk, show in /api/voices and the library, filter, and vanish when a voice is deleted."""
    rec = client.post(
        "/api/voicelab/design/save",
        json={"recipe": recipe(("af_heart", 1), ("am_michael", 1)), "name": "Star me", "kind": "blend"},
    ).json()
    mine = rec["id"]
    cat = {v["id"]: v for v in client.get("/api/voices").json()["catalog"]}
    assert cat["af_heart"]["starred"] is False and cat[mine]["starred"] is False

    for vid in ("af_heart", mine):
        r = client.put(f"/api/voicelab/voices/{vid}/star", json={"starred": True})
        assert r.status_code == 200 and r.json() == {"id": vid, "starred": True}
    assert set(vlib.favorites()) == {"af_heart", mine}
    assert (tmp_path / "favorites.json").exists()

    cat = {v["id"]: v for v in client.get("/api/voices").json()["catalog"]}
    assert cat["af_heart"]["starred"] and cat[mine]["starred"] and not cat["am_michael"]["starred"]
    lib = client.get("/api/voicelab/library?kind=starred").json()["voices"]
    assert {v["id"] for v in lib} == {"af_heart", mine}

    # Unstar, unknown ids and junk are refused without touching the file.
    assert client.put("/api/voicelab/voices/af_heart/star", json={"starred": False}).status_code == 200
    assert client.put("/api/voicelab/voices/not_a_voice/star", json={"starred": True}).status_code == 404
    assert client.put("/api/voicelab/voices/custom:000000000000/star", json={"starred": True}).status_code == 404
    assert client.put("/api/voicelab/voices/af_heart/star", json={"starred": "maybe"}).status_code == 422
    assert vlib.favorites() == {mine}

    # Deleting a voice removes its star; a corrupt favourites file never breaks the catalog.
    assert client.delete(f"/api/voicelab/voices/{mine}").status_code == 200
    assert vlib.favorites() == set()
    (tmp_path / "favorites.json").write_text("{not json")
    assert vlib.favorites() == set()
    assert client.get("/api/voices").status_code == 200
