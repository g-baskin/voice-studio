"""API routes for /api/voicelab (registered in server.py). Errors never include filesystem paths."""
from __future__ import annotations

import logging
import math
import shutil
import tempfile
import threading
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import voicelab as vl
from . import voices as vlib

router = APIRouter(prefix="/api/voicelab")
log = logging.getLogger(__name__)
MAX_UPLOAD = 100 * 1024 * 1024
UPLOAD_EXTS = {".wav", ".mp3", ".m4a", ".mp4"}
MIN_REF_S, MAX_REF_S = 10.0, 60.0
BUDGETS = (5, 600)  # seconds; UI offers 1, 3, 5, 10 minutes
match_jobs: dict[str, dict] = {}
WORK = Path(tempfile.gettempdir()) / "naturalvoice-voicelab"


def _busy():
    from .server import processing

    if not processing.acquire(blocking=False):
        raise HTTPException(429, "Another voice job is running. Wait for it to finish, then retry.")
    return processing


def _wav(audio, name="voice-lab.wav") -> FileResponse:
    from . import audio as au

    WORK.mkdir(exist_ok=True)
    p = WORK / f"{uuid.uuid4().hex}.wav"
    au.save(p, audio, vl.SR)
    return FileResponse(p, media_type="audio/wav", filename=name)


def _check_text(text: str | None, lang: str) -> str:
    text = (text or "").strip() or vl.sample_text(lang)
    if len(text) > vl.MAX_TEXT:
        raise HTTPException(400, f"Preview text is too long ({vl.MAX_TEXT} characters max).")
    return text


def _recipe_gender(recipe: dict) -> str:
    g = {"female": 0.0, "male": 0.0}
    for v in recipe["voices"]:
        if ":" not in v["id"]:
            g[vlib.stock_info(v["id"])["gender"]] += v["weight"]
    g["female"] += recipe.get("controls", {}).get("gender", 0)
    return "female" if g["female"] >= g["male"] else "male"


# ------------------------------------------------------------------ library

@router.get("/library")
def library(language: str = "", gender: str = "", kind: str = "", q: str = ""):
    try:
        items = vl.library()
    except RuntimeError:
        raise HTTPException(503, "The voice model files are missing. See the README to download them.")
    q = q.strip().lower()[:60]
    if kind == "starred":
        items_f = [r for r in items if r.get("starred")]
    else:
        items_f = items
    out = [r for r in items_f
           if (not language or r.get("language") == language) and (not gender or r.get("gender") == gender)
           and (not kind or kind == "starred" or r.get("kind") == kind) and (not q or q in (r["name"] + " " + r["id"]).lower())]
    return {"voices": out, "total": len(items),
            "languages": sorted({r.get("language", "Other") for r in items}),
            "controls": {k: {kk: vv for kk, vv in c.items() if kk != "scale"} for k, c in vl.CONTROLS.items()}}


def _known(voice_id: str) -> dict:
    if voice_id.startswith(("custom:", "clone:")):
        try:
            return vlib.get(voice_id)
        except (KeyError, ValueError):
            raise HTTPException(404, "That voice is not in the library.")
    try:
        names = vl._stock_names()
    except RuntimeError:
        raise HTTPException(503, "The voice model files are missing.")
    if voice_id not in names:
        raise HTTPException(404, "That voice is not in the library.")
    return vlib.stock_info(voice_id)


@router.get("/preview")
def preview(voice: str):
    rec = _known(voice[:80])
    if rec.get("kind") == "clone":
        raise HTTPException(400, "Clone voices are previewed in the Clone section.")
    p = vl.preview_path(voice)
    if not p.exists():
        sem = _busy()
        try:
            vl.render_preview(voice)
        except Exception:
            log.exception("preview failed")
            raise HTTPException(500, "Could not render a preview for this voice.")
        finally:
            sem.release()
    return FileResponse(p, media_type="audio/wav", headers={"Cache-Control": "no-cache"})


class Rename(BaseModel):
    name: str = Field(min_length=1, max_length=60)


@router.post("/voices/{voice_id}/rename")
def rename(voice_id: str, body: Rename):
    if not voice_id.startswith(("custom:", "clone:")):
        raise HTTPException(400, "Stock voices can't be renamed.")
    _known(voice_id)
    try:
        return vlib.rename(voice_id, body.name)
    except ValueError as e:
        raise HTTPException(400, str(e))


class Star(BaseModel):
    starred: bool


@router.put("/voices/{voice_id}/star")
def star(voice_id: str, body: Star):
    _known(voice_id[:80])  # only real voices can be starred; keeps favorites.json free of junk
    vlib.set_starred(voice_id, body.starred)
    return {"id": voice_id, "starred": body.starred}


@router.delete("/voices/{voice_id}")
def delete(voice_id: str):
    if not voice_id.startswith(("custom:", "clone:")):
        raise HTTPException(400, "Stock voices can't be deleted.")
    _known(voice_id)
    vlib.delete(voice_id)
    vl.drop_preview(voice_id)
    return {"deleted": voice_id}


@router.get("/voices/{voice_id}")
def voice(voice_id: str):
    return _known(voice_id)


# ------------------------------------------------------------------ design (blend)

class Design(BaseModel):
    recipe: dict
    text: str | None = Field(default=None, max_length=1000)
    name: str | None = Field(default=None, max_length=60)
    kind: str = "blend"


def _build(recipe: dict):
    try:
        return vl.build_style(recipe)
    except (ValueError, KeyError) as e:
        raise HTTPException(400, str(e).strip("'\""))
    except RuntimeError:
        raise HTTPException(503, "The voice model files are missing.")


@router.post("/design/preview")
def design_preview(body: Design):
    style, lang = _build(body.recipe)
    text = _check_text(body.text, lang)
    sem = _busy()
    try:
        a = vl.render(style, lang, text)
    except Exception:
        log.exception("design preview failed")
        raise HTTPException(500, "Could not render this voice. Try a different blend.")
    finally:
        sem.release()
    return _wav(a, "voice-design-preview.wav")


@router.post("/design/save")
def design_save(body: Design):
    style, lang = _build(body.recipe)
    if body.kind not in {"blend", "describe"}:
        raise HTTPException(400, "Unknown design kind.")
    recipe = vl.validate_recipe(body.recipe)
    try:
        return vlib.save_custom(body.name or "", style, lang=lang,
                                meta={"source": body.kind, "recipe": recipe, "gender": _recipe_gender(recipe)})
    except ValueError as e:
        raise HTTPException(400, str(e))


# ------------------------------------------------------------------ describe

class Describe(BaseModel):
    prompt: str = Field(default="", max_length=vl.MAX_TEXT)
    gender: str = ""
    accent: str = ""
    age: str = ""
    energy: str = ""
    seed: int | None = Field(default=None, ge=0, lt=2 ** 32)


@router.post("/describe")
def describe(body: Describe):
    if body.gender not in {"", "female", "male"} or body.accent not in {"", *vlib.LANGS} \
            or body.age not in {"", "young", "adult", "older"} or body.energy not in {"", "calm", "neutral", "energetic"}:
        raise HTTPException(400, "Unknown option in the voice description.")
    if not body.prompt.strip() and not any([body.gender, body.accent, body.age, body.energy]):
        raise HTTPException(400, "Describe the voice or pick at least one option.")
    try:
        return vl.describe(body.prompt, body.gender, body.accent, body.age, body.energy, 3, body.seed)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError:
        raise HTTPException(503, "The voice model files are missing.")


# ------------------------------------------------------------------ match a recording

@router.post("/match")
async def match_start(file: UploadFile = File(...), consent: str = Form(""), budget: float = Form(180)):
    if consent.lower() not in {"true", "1", "on", "yes"}:
        raise HTTPException(400, "Confirm that you own this voice or have permission to use it.")
    if not math.isfinite(budget) or not BUDGETS[0] <= budget <= BUDGETS[1]:
        raise HTTPException(400, f"Search time must be between {BUDGETS[0]} and {BUDGETS[1]} seconds.")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in UPLOAD_EXTS:
        raise HTTPException(400, "Upload a WAV, MP3, M4A or MP4 recording.")
    sem = _busy()
    job = uuid.uuid4().hex
    d = WORK / job
    src = d / f"ref{suffix}"
    try:
        d.mkdir(parents=True)
        size = 0
        with src.open("wb") as fh:
            while chunk := await file.read(1 << 20):
                size += len(chunk)
                if size > MAX_UPLOAD:
                    raise HTTPException(413, "Recording too large (100 MB max).")
                fh.write(chunk)
        if not size:
            raise HTTPException(400, "The uploaded file is empty.")
        from . import audio as au

        try:
            ref, sr = au.load(src)
        except Exception:
            raise HTTPException(400, "Could not read this recording. Try converting it to WAV.")
        ref = ref.mean(axis=1)
        dur = len(ref) / sr
        if not MIN_REF_S <= dur <= MAX_REF_S + 0.5:
            raise HTTPException(400, f"The recording is {dur:.0f} s long; use 10 to 60 seconds of clear speech.")
    except BaseException:
        shutil.rmtree(d, ignore_errors=True)
        sem.release()
        raise
    finally:
        await file.close()
    cancel = threading.Event()
    match_jobs[job] = {"status": "running", "step": "Starting", "progress": 0.0, "started": time.time(),
                       "budget": budget, "_cancel": cancel, "_dir": d}

    def run():
        j = match_jobs[job]
        try:
            res = vl.match(ref, sr, budget, progress=lambda **kw: j.update(kw), cancel=cancel)
            j["_style"] = res.pop("style")
            j["_start"] = res.pop("start_style")
            j.update(status="done", progress=1.0, step="Done", result=res)
        except vl.Cancelled:
            j.update(status="cancelled", step="Cancelled")
        except Exception:
            log.exception("match job failed")
            j.update(status="error", error="Matching failed. Try a cleaner recording of one speaker.")
        finally:
            sem.release()

    threading.Thread(target=run, daemon=True).start()
    return {"job": job}


def _job(job: str) -> dict:
    j = match_jobs.get(job)
    if not j:
        raise HTTPException(404, "No such match job.")
    return j


@router.get("/match/{job}")
def match_status(job: str):
    j = _job(job)
    out = {k: v for k, v in j.items() if not k.startswith("_")}
    out["elapsed"] = round(time.time() - j["started"], 1)
    return out


@router.post("/match/{job}/cancel")
def match_cancel(job: str):
    j = _job(job)
    j["_cancel"].set()
    return {"status": j["status"]}


@router.get("/match/{job}/audio")
def match_audio(job: str, which: str = "after"):
    j = _job(job)
    if j["status"] != "done" or which not in {"before", "after", "reference"}:
        raise HTTPException(404, "Audio not available.")
    if which == "reference":
        return FileResponse(next(j["_dir"].glob("ref.*")))
    style = j["_style"] if which == "after" else j["_start"]
    sem = _busy()
    try:
        a = vl.render(style, "en-us", vl.sample_text("en-us"))
    finally:
        sem.release()
    return _wav(a, f"match-{which}.wav")


class SaveMatch(BaseModel):
    name: str = Field(min_length=1, max_length=60)


@router.post("/match/{job}/save")
def match_save(job: str, body: SaveMatch):
    j = _job(job)
    if j["status"] != "done":
        raise HTTPException(400, "The match job has not finished.")
    r = j["result"]
    try:
        return vlib.save_custom(body.name, j["_style"], lang="en-us",
                                meta={"source": "match", "similarity_before": r["before"],
                                      "similarity_after": r["after"], "best_stock": r["best_stock"],
                                      "consent": True})
    except ValueError as e:
        raise HTTPException(400, str(e))
