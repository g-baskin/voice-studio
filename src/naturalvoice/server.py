"""Local web app (also installable on a phone as a PWA when served on your network)."""

from __future__ import annotations

import contextlib
import math
import logging
import re
import zipfile
import shutil
import tempfile
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask
from pydantic import BaseModel, Field

from . import access, audio, humanize as hz

WEB = Path(__file__).parent / "web"
# SvelteKit build of the pages already migrated (source: frontend/); the rest are plain HTML in WEB.
UI = Path(__file__).parent / "ui"
WORK = Path(tempfile.gettempdir()) / "naturalvoice"
WORK.mkdir(exist_ok=True)
MAX_BYTES = 500 * 1024 * 1024
KEEP_JOBS = 50  # finished jobs kept for download; more than one full 20-file batch
STALE_SECONDS = 86400
# Only names this module creates are ever removed from WORK.
JOB_DIR = re.compile(r"[0-9a-f]{32}")
SCRATCH_FILE = re.compile(r"(?:speech-[0-9a-f]{32}\.wav|batch-[0-9a-f]{32}\.zip)")

app = FastAPI(title="Shark Audio")
jobs: dict[str, dict] = {}
# One processing job at a time bounds CPU/memory; the browser batch queue is sequential.
processing = threading.BoundedSemaphore(1)


def _prune() -> None:
    """Drop the oldest finished jobs, then files that earlier server runs left behind."""
    finished = [k for k, j in list(jobs.items()) if j["status"] != "running"]
    for k in finished[: max(len(finished) - KEEP_JOBS, 0)]:
        shutil.rmtree(WORK / k, ignore_errors=True)
        jobs.pop(k, None)
    cutoff = time.time() - STALE_SECONDS
    for p in sorted(WORK.iterdir()):
        with contextlib.suppress(FileNotFoundError):
            if p.stat().st_mtime >= cutoff:
                continue
            if p.is_dir() and JOB_DIR.fullmatch(p.name) and p.name not in jobs:
                shutil.rmtree(p, ignore_errors=True)
            elif p.is_file() and SCRATCH_FILE.fullmatch(p.name):
                p.unlink()


def _settings_from_form(preset, **kw):
    values = {k: float(v) for k, v in kw.items() if v not in (None, "")}
    if any(not math.isfinite(v) or not 0 <= v <= 1 for v in values.values()):
        raise ValueError("Cleanup controls must be finite numbers from 0 to 1.")
    return hz.get_settings(preset, **values)


@app.get("/api/presets")
def presets():
    return {k: v.to_dict() for k, v in hz.PRESETS.items()}


@app.get("/api/voices")
def list_voices():
    from . import voices as vlib

    try:
        cat = vlib.catalog()
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    # 'voices' (ids) kept for older pages; 'catalog' has names, kinds and languages.
    return {"voices": [v["id"] for v in cat], "catalog": cat}


@app.post("/api/clean")
async def clean(
    file: UploadFile = File(...),
    preset: str = Form("standard"),
    ai_clean: str = Form(None),
    dereverb: str = Form(None),
    demetal: str = Form(None),
    deharsh: str = Form(None),
    warmth: str = Form(None),
    denoise: str = Form(None),
    room_tone: str = Form(None),
    mode: str = Form("clean"),
    start: float = Form(0),
    seconds: float = Form(15),
):
    try:
        settings = _settings_from_form(
            preset,
            ai_clean=ai_clean,
            dereverb=dereverb,
            demetal=demetal,
            deharsh=deharsh,
            warmth=warmth,
            denoise=denoise,
            room_tone=room_tone,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    if mode not in {"clean", "preview", "analyze"} or not math.isfinite(start) or not 0 <= start <= 86400:
        raise HTTPException(400, "Invalid operation or preview start time.")
    if not math.isfinite(seconds) or not 10 <= seconds <= 20:
        raise HTTPException(400, "Preview length must be between 10 and 20 seconds.")
    suffix = Path(file.filename or "in.wav").suffix.lower() or ".wav"
    if suffix not in audio.VIDEO_EXTS | {".wav", ".flac", ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".aiff", ".aif"}:
        raise HTTPException(400, "Unsupported audio/video file type.")
    if not processing.acquire(blocking=False):
        raise HTTPException(429, "Another file is processing. Wait for it to finish, then retry.")
    try:
        _prune()
    except BaseException:
        processing.release()
        raise
    job = uuid.uuid4().hex
    d = WORK / job
    src = d / f"input{suffix}"
    try:
        d.mkdir()
        size = 0
        with src.open("wb") as fh:
            while chunk := await file.read(1 << 20):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise HTTPException(413, "File too large (500 MB max).")
                fh.write(chunk)
        if not size:
            raise HTTPException(400, "The uploaded file is empty.")
    except BaseException:
        shutil.rmtree(d, ignore_errors=True)
        processing.release()
        raise
    finally:
        await file.close()
    dst = d / (f"natural{suffix}" if mode == "clean" and audio.is_video(src) else "natural.wav")
    jobs[job] = {"status": "running", "step": "Starting", "progress": 0.0, "name": file.filename, "mode": mode}

    def run():
        from .workflow import AudioInputError, process

        def prog(name, f):
            jobs[job].update(step=name, progress=round(f, 2))

        try:
            res = process(src, dst, settings, mode, start, seconds, prog)
            jobs[job].update(status="done", progress=1.0, result=res, output=str(dst))
        except Exception as e:
            logging.getLogger(__name__).exception("Audio job failed")
            public = (
                str(e)
                if isinstance(e, AudioInputError)
                else (
                    "Could not process this recording. Check that it contains playable audio, or try converting it to WAV/MP4."
                )
            )
            jobs[job].update(status="error", error=public)
        finally:
            processing.release()

    threading.Thread(target=run, daemon=True).start()
    return {"job": job}


@app.get("/api/jobs/{job}")
def job_status(job: str):
    j = jobs.get(job)
    if not j:
        raise HTTPException(404, "No such job")
    return JSONResponse({k: v for k, v in j.items() if k != "output"})


@app.get("/api/jobs/{job}/{which}")
def job_file(job: str, which: str):
    j = jobs.get(job)
    if not j:
        raise HTTPException(404, "No such job")
    d = WORK / job
    if which in {"compare-before", "compare-after"} and j.get("status") == "done" and j.get("mode") != "analyze":
        return FileResponse(d / f"{which}.wav", media_type="audio/wav")
    if which == "original":
        files = list(d.glob("input.*"))
        if not files:
            raise HTTPException(404)
        return FileResponse(files[0])
    if which == "result" and j.get("status") == "done" and j.get("mode") != "analyze":
        out = Path(j["output"])
        name = (
            Path(j.get("name") or "voice").stem
            + (".preview" if j.get("mode") == "preview" else ".natural")
            + out.suffix
        )
        return FileResponse(out, filename=name)
    raise HTTPException(404)


class BatchDownload(BaseModel):
    jobs: list[str] = Field(min_length=1, max_length=20)


@app.post("/api/batch-download")
def batch_download(request: BatchDownload):
    selected = []
    for key in dict.fromkeys(request.jobs):
        job = jobs.get(key) if re.fullmatch(r"[0-9a-f]{32}", key) else None
        if not job or job.get("status") != "done" or job.get("mode") != "clean":
            raise HTTPException(400, "Only completed full-file jobs can be downloaded together.")
        selected.append(job)
    path = WORK / f"batch-{uuid.uuid4().hex}.zip"
    try:
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
            for i, job in enumerate(selected, 1):
                out = Path(job["output"])
                safe = re.sub(r"[^A-Za-z0-9._-]", "_", Path(job.get("name") or "voice").stem)[:100] or "voice"
                archive.write(out, f"{i:02d}-{safe}.natural{out.suffix}")
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return FileResponse(
        path,
        media_type="application/zip",
        filename="natural-voice-batch.zip",
        background=BackgroundTask(path.unlink, missing_ok=True),
    )


@app.post("/api/speak")
def speak(
    text: str = Form(...),
    voice: str = Form("af_heart"),
    speed: float = Form(1.0),
    engine: str = Form("kokoro"),
    humanize: bool = Form(True),
):
    from . import tts

    if not text.strip():
        raise HTTPException(400, "Text is empty.")
    if len(text) > 20000:
        raise HTTPException(400, "Text too long (20,000 characters max).")
    try:
        out, sr = tts.speak(text, voice, speed, engine, humanize=humanize)
    except (RuntimeError, ValueError) as e:
        raise HTTPException(400, str(e))
    path = WORK / f"speech-{uuid.uuid4().hex}.wav"
    try:
        audio.save(path, out, sr)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return FileResponse(
        path,
        media_type="audio/wav",
        filename="natural-voice.wav",
        background=BackgroundTask(path.unlink, missing_ok=True),
    )


# Feature routers must be registered before the static mount, which catches everything else.
from . import clone_api, llm_api, rewrite_api, sample_library_api, scriptgen_api, studio_api, voicelab_api  # noqa: E402

from . import backup_api  # noqa: E402
from . import shark_api  # noqa: E402

app.add_middleware(backup_api.BackupGate)
app.add_middleware(sample_library_api.SampleUploadLimit)
# Added last so it runs first: nothing, including the upload limit, sees a refused request.
app.add_middleware(access.LocalAccess)

for _r in (
    backup_api.router,
    shark_api.router,
    voicelab_api.router,
    studio_api.router,
    clone_api.router,
    sample_library_api.router,
    rewrite_api.router,
    scriptgen_api.router,
    llm_api.router,
):
    app.include_router(_r)

# Clean page addresses; the old .html addresses redirect so bookmarks keep working.
PAGES = {
    "/": WEB / "index.html",
    "/studio": WEB / "studio.html",
    "/voice-lab": WEB / "voicelab.html",
    "/samples": WEB / "samples.html",
    "/speak": UI / "speak.html",
    "/backup": UI / "backup.html",
}
OLD_ADDRESSES = {
    "/index.html": "/",
    "/studio.html": "/studio",
    "/voicelab.html": "/voice-lab",
    "/samples.html": "/samples",
    "/backup.html": "/backup",
}


def _serve_page(path: Path):
    def page() -> FileResponse:
        return FileResponse(path, media_type="text/html", headers={"Cache-Control": "no-cache"})

    return page


def _redirect_to(target: str):
    # Temporary redirects: a browser must not cache them if this app is rolled back.
    def moved(request: Request) -> RedirectResponse:
        query = request.url.query
        return RedirectResponse(target + (f"?{query}" if query else ""), status_code=302)

    return moved


for _path, _file in PAGES.items():
    app.add_api_route(_path, _serve_page(_file), methods=["GET", "HEAD"], include_in_schema=False)
for _old, _new in OLD_ADDRESSES.items():
    app.add_api_route(_old, _redirect_to(_new), methods=["GET", "HEAD"], include_in_schema=False)

app.mount("/_app", StaticFiles(directory=UI / "_app"), name="ui")
app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
