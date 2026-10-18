"""API routes for /api/clone (registered in server.py).

GET  /api/clone/status                 engine status (installed, model, licence, sample rate, device, setup hint)
POST /api/clone/voices                 multipart: name, file, consent=true, transcript? -> voice record (201)
POST /api/clone/preview                form: voice, text (<=500 chars, may contain emotion tags), speed?, language? (en|es|fr|it|pt)
                                       -> {"job": id, "warning"?} (202); unknown [tags] are removed and named in warning
GET  /api/clone/preview/{job}          {"status": running|done|error, "progress", "step", "error"?, "seconds"?}
GET  /api/clone/preview/{job}/audio    WAV once done
POST /api/clone/convert                multipart: voice, file (1-60 s performance), consent=true -> {"job": id} (202)
GET  /api/clone/convert/{job}[/audio]  same shapes as preview (voice changer)
"""
from __future__ import annotations

import logging
import math
import re
import shutil
import tempfile
import threading
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

router = APIRouter(prefix="/api/clone")
log = logging.getLogger(__name__)

MAX_BYTES = 50 * 1024 * 1024
EXTS = {".wav", ".mp3", ".m4a", ".mp4", ".webm", ".ogg", ".oga", ".opus"}
MAX_PREVIEW = 500
WORK = Path(tempfile.gettempdir()) / "naturalvoice-clone"
_JOB = re.compile(r"^[0-9a-f]{32}$")
jobs: dict[str, dict] = {}
_MAX_JOBS = 50


@router.get("/status")
def status():
    from . import clone

    return clone.status()


def _truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in {"true", "1", "yes", "on"}


@router.post("/voices", status_code=201)
async def create_voice(name: str = Form(""), consent: str = Form(""), transcript: str = Form(""),
                       file: UploadFile = File(None)):
    from . import clone, voices

    try:
        if not _truthy(consent):
            raise HTTPException(400, "Confirm that you own this voice or have permission to clone it.")
        name = (name or "").strip()
        if not name or len(name) > 60:
            raise HTTPException(400, "Give the voice a name (1 to 60 characters).")
        transcript = (transcript or "").strip()
        if len(transcript) > 2000:
            raise HTTPException(400, "Transcript too long (2,000 characters max).")
        if file is None or not file.filename:
            raise HTTPException(400, "Choose or record a reference recording.")
        suffix = Path(file.filename).suffix.lower()
        if suffix not in EXTS:
            raise HTTPException(400, "Unsupported file type. Use WAV, MP3, M4A, MP4, WebM or OGG.")
        WORK.mkdir(parents=True, exist_ok=True)
        d = Path(tempfile.mkdtemp(dir=WORK))
        try:
            src, size = d / f"in{suffix}", 0
            with src.open("wb") as fh:
                while chunk := await file.read(1 << 20):
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise HTTPException(413, "File too large (50 MB max).")
                    fh.write(chunk)
            if not size:
                raise HTTPException(400, "The uploaded file is empty.")
            ref = d / "ref.wav"
            try:
                info = clone.prepare_reference(src, ref)
            except ValueError as e:
                raise HTTPException(400, str(e))
            except Exception:
                log.exception("Reference preprocessing failed")
                raise HTTPException(400, "Could not read this recording. Try WAV, MP3, M4A, WebM or OGG.")
            meta = {**info, "engine": clone.MODEL_NAME, "consent": True, "consent_at": time.time()}
            if transcript:
                meta["transcript"] = transcript
            return voices.save_clone(name, ref, meta, "en-us")
        finally:
            shutil.rmtree(d, ignore_errors=True)
    finally:
        if file is not None:
            await file.close()


@router.post("/preview", status_code=202)
def preview(voice: str = Form(""), text: str = Form(""), speed: float = Form(1.0), language: str = Form("en")):
    from . import clone, voices

    text, removed = clone.clean_tags((text or "").strip())
    if not text:
        raise HTTPException(400, "Type some text to preview.")
    if len(text) > MAX_PREVIEW:
        raise HTTPException(400, f"Preview text is limited to {MAX_PREVIEW} characters.")
    if not math.isfinite(speed) or not 0.5 <= speed <= 2.0:
        raise HTTPException(400, "Speed must be between 0.5 and 2.")
    language = (language or "en").strip().lower()
    if language not in clone.LANGUAGES:
        raise HTTPException(400, f"Unsupported language. Choose one of: {', '.join(clone.LANGUAGES)}.")
    _check_voice(voice)
    warning = (f"Removed unsupported tag{'s' if len(removed) > 1 else ''} {', '.join(dict.fromkeys(removed))[:200]}. "
               f"Supported: {' '.join(clone.EMOTION_TAGS)}") if removed else None
    if language != "en":
        return _start_job(lambda prog: clone.speak_language(text, voice, language, speed, progress=prog), "preview",
                          warning=warning)
    return _start_job(lambda prog: clone.speak(text, voice, speed, progress=prog), "preview", warning=warning)


def _check_voice(voice: str):
    from . import clone, voices

    if not voice.startswith("clone:"):
        raise HTTPException(400, "Choose a cloned voice.")
    try:
        voices.get(voice)
    except ValueError:
        raise HTTPException(400, "Invalid voice id.")
    except KeyError:
        raise HTTPException(404, "Voice not found.")
    if not clone.installed():
        raise HTTPException(503, "The voice cloning engine is not installed. " + clone.SETUP_HINT)


def _start_job(render, kind: str, cleanup=None, warning: str | None = None):
    """Run render(progress) -> (wav, sr) in the background under the shared processing lock."""
    from . import clone
    from .server import processing

    if not processing.acquire(blocking=False):
        if cleanup:
            cleanup()
        raise HTTPException(429, "Another job is running. Wait for it to finish, then retry.")
    job = uuid.uuid4().hex
    for old in list(jobs)[:-_MAX_JOBS]:
        j = jobs.pop(old, {})
        if j.get("output"):
            Path(j["output"]).unlink(missing_ok=True)
    jobs[job] = {"status": "running", "kind": kind, "progress": 0.0, "step": "Starting the cloning engine"}
    if warning:
        jobs[job]["warning"] = warning

    def run():
        from . import audio

        t = time.time()
        try:
            def prog(f, step):
                jobs[job].update(progress=round(f, 2), step=step)
            wav, sr = render(prog)
            WORK.mkdir(parents=True, exist_ok=True)
            out = WORK / f"{kind}-{job}.wav"
            audio.save(out, wav, sr)
            jobs[job].update(status="done", progress=1.0, step="Done", output=str(out),
                             seconds=round(len(wav) / sr, 2), render_seconds=round(time.time() - t, 1))
        except Exception as e:
            log.exception("Clone %s failed", kind)
            msg = str(e) if isinstance(e, (ValueError, clone.EngineMissing)) else \
                "The cloning engine could not process this. Try a shorter clip."
            jobs[job].update(status="error", error=msg)
        finally:
            processing.release()
            if cleanup:
                cleanup()

    threading.Thread(target=run, daemon=True).start()
    return {"job": job, **({"warning": warning} if warning else {})}


@router.post("/convert", status_code=202)
async def convert(voice: str = Form(""), consent: str = Form(""), file: UploadFile = File(None)):
    """Voice changer: re-voice an uploaded performance (1-60 s) in a clone voice."""
    from . import clone

    try:
        if not _truthy(consent):
            raise HTTPException(400, "Confirm that you have the rights to this performance and to the target voice.")
        if file is None or not file.filename:
            raise HTTPException(400, "Choose or record a performance to convert.")
        suffix = Path(file.filename).suffix.lower()
        if suffix not in EXTS:
            raise HTTPException(400, "Unsupported file type. Use WAV, MP3, M4A, MP4, WebM or OGG.")
        _check_voice(voice)
        WORK.mkdir(parents=True, exist_ok=True)
        d = Path(tempfile.mkdtemp(dir=WORK))
        cleanup = lambda: shutil.rmtree(d, ignore_errors=True)
        try:
            src, size = d / f"in{suffix}", 0
            with src.open("wb") as fh:
                while chunk := await file.read(1 << 20):
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise HTTPException(413, "File too large (50 MB max).")
                    fh.write(chunk)
            if not size:
                raise HTTPException(400, "The uploaded file is empty.")
            prepared = d / "source.wav"
            try:
                clone.prepare_source(src, prepared)
            except ValueError as e:
                raise HTTPException(400, str(e))
            except Exception:
                log.exception("Source preprocessing failed")
                raise HTTPException(400, "Could not read this recording. Try WAV, MP3, M4A, WebM or OGG.")
        except BaseException:
            cleanup()
            raise
        return _start_job(lambda prog: clone.convert(prepared, voice, progress=prog), "convert", cleanup)
    finally:
        if file is not None:
            await file.close()


def _job(job: str) -> dict:
    j = jobs.get(job) if _JOB.match(job) else None
    if not j:
        raise HTTPException(404, "No such preview.")
    return j


@router.get("/convert/{job}")
@router.get("/preview/{job}")
def preview_status(job: str):
    return JSONResponse({k: v for k, v in _job(job).items() if k != "output"})


@router.get("/convert/{job}/audio")
@router.get("/preview/{job}/audio")
def preview_audio(job: str):
    j = _job(job)
    if j.get("status") != "done":
        raise HTTPException(409, "The preview is not ready yet.")
    return FileResponse(j["output"], media_type="audio/wav", filename=f"clone-{j.get('kind', 'preview')}.wav")
