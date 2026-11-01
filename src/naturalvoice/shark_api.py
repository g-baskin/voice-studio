"""API routes for /api/shark: plan, perform chunk by chunk, retake, revise and download."""

from __future__ import annotations

import logging
import re
import shutil
import tempfile
import threading
import time
from pathlib import Path

import numpy as np
import soundfile as sf
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import shark
from . import studio as st

router = APIRouter(prefix="/api/shark")
log = logging.getLogger(__name__)
WORK = Path(tempfile.gettempdir()) / "naturalvoice-shark"
KEEP_JOBS = 8
MAX_VERSIONS = 12
HEX32 = re.compile(r"^[0-9a-f]{32}$")
jobs: dict[str, dict] = {}
# Revisions and the background renderer both touch a job's chunk list.
_lock = threading.Lock()


class Script(BaseModel):
    model_config = ConfigDict(extra="forbid")
    script: str = Field(min_length=1, max_length=shark.MAX_CHARS)
    voice: str = "af_heart"
    cast: dict[str, str] = Field(default_factory=dict, max_length=shark.MAX_SPEAKERS)

    @field_validator("voice")
    @classmethod
    def _voice(cls, v: str) -> str:
        if not st.VOICE_ID.match(v):
            raise ValueError("unknown voice id")
        return v

    @field_validator("cast")
    @classmethod
    def _cast(cls, d: dict[str, str]) -> dict[str, str]:
        for name, voice in d.items():
            if len(name) > 60 or not st.VOICE_ID.match(voice):
                raise ValueError("cast entries need a speaker name up to 60 characters and a known voice id")
        return d


class Revision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instruction: str = Field("", max_length=200)
    retake: bool = False


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=0, lt=MAX_VERSIONS)


def _plan(req: Script) -> list[shark.Chunk]:
    try:
        return shark.plan(req.script, req.cast, req.voice)
    except shark.SharkError as e:
        raise HTTPException(400, str(e)) from None


def _busy():
    from .server import processing

    if not processing.acquire(blocking=False):
        raise HTTPException(429, "Another render or file is processing. Wait for it to finish, then retry.")
    return processing


def _job(job: str) -> dict:
    j = jobs.get(job) if HEX32.match(job) else None
    if not j:
        raise HTTPException(404, "No such performance. It may have expired; perform the script again.")
    return j


def _prune() -> None:
    finished = [k for k, j in list(jobs.items()) if j["status"] != "running"]
    for k in finished[: max(len(finished) - KEEP_JOBS + 1, 0)]:
        shutil.rmtree(WORK / k, ignore_errors=True)
        jobs.pop(k, None)


def _public_error(e: Exception) -> str:
    if isinstance(e, (RuntimeError, ValueError, KeyError)):
        return str(e).strip("'\"") or "The voice engine failed on this chunk."
    log.exception("Shark chunk failed unexpectedly")
    return "The voice engine failed on this chunk."


class VersionLimit(Exception):
    """A chunk reached MAX_VERSIONS while a revision waited for the lock."""


class JobGone(Exception):
    """The job was pruned while a revision waited for the render slot."""


def _render_version(job: str, index: int, line: dict, take: int, note: str) -> dict:
    """Render one version of a chunk to disk. Call with _lock held. Raises on engine failure."""
    if job not in jobs:
        raise JobGone
    entry = jobs[job]["chunks"][index]
    # Checked again under the lock: two revisions can both pass the earlier, unlocked check.
    if len(entry["versions"]) >= MAX_VERSIONS:
        raise VersionLimit(f"This chunk already has {MAX_VERSIONS} versions. Pick one or perform again.")
    audio = shark.render(line, take)
    version = len(entry["versions"])
    path = WORK / job / f"{index}-{version}.wav"
    sf.write(path, np.clip(audio, -1, 1), st.SR, subtype="PCM_16")
    record = {"version": version, "take": take, "note": note, "seconds": round(len(audio) / st.SR, 2)}
    entry["versions"].append(record)
    entry["lines"].append(line)
    entry["selected"] = version
    return record


def _view(job: str) -> dict:
    j = jobs[job]
    return {
        "job": job,
        "status": j["status"],
        "error": j.get("error"),
        "chunks": [
            {
                **c["plan"],
                "state": c["state"],
                "error": c.get("error"),
                "versions": c["versions"],
                "selected": c["selected"],
            }
            for c in j["chunks"]
        ],
    }


@router.get("/directions")
def directions():
    return {
        "directions": [{"tag": k, "exact": d.exact, "note": d.note} for k, d in shark.DIRECTIONS.items()],
        "clone_tags": st.clone_emotion_tags(),
    }


@router.post("/plan")
def plan(req: Script):
    return {"chunks": [c.as_dict() for c in _plan(req)]}


@router.post("/perform")
def perform(req: Script):
    chunks = _plan(req)
    sem = _busy()
    try:
        with _lock:
            _prune()
            job = shark.new_job_id()
            (WORK / job).mkdir(parents=True)
            cancel = threading.Event()
            jobs[job] = {
                "status": "running",
                "created": time.time(),
                "cancel": cancel,
                "chunks": [
                    {"plan": c.as_dict(), "chunk": c, "state": "waiting", "versions": [], "lines": [], "selected": None}
                    for c in chunks
                ],
            }
    except BaseException:
        sem.release()
        raise

    def run() -> None:
        try:
            for i, entry in enumerate(jobs[job]["chunks"]):
                if cancel.is_set():
                    break
                entry["state"] = "rendering"
                try:
                    with _lock:
                        _render_version(job, i, entry["chunk"].line, 0, "first take")
                    entry["state"] = "ready"
                except Exception as e:  # one failing chunk must not stop the rest of the performance
                    entry.update(state="error", error=_public_error(e))
            jobs[job]["status"] = "cancelled" if cancel.is_set() else "done"
        except Exception:
            log.exception("Shark performance failed")
            jobs[job].update(status="error", error="The performance failed. Try a shorter script, then retry.")
        finally:
            sem.release()

    threading.Thread(target=run, daemon=True).start()
    return {"job": job}


@router.get("/jobs/{job}")
def status(job: str):
    _job(job)
    return _view(job)


@router.post("/jobs/{job}/cancel")
def cancel(job: str):
    _job(job)["cancel"].set()
    return {"ok": True}


def _entry(job: str, index: int) -> dict:
    chunks = _job(job)["chunks"]
    if not 0 <= index < len(chunks):
        raise HTTPException(404, "No such chunk.")
    return chunks[index]


@router.post("/jobs/{job}/chunks/{index}/revise")
def revise(job: str, index: int, req: Revision):
    j = _job(job)
    entry = _entry(job, index)
    if j["status"] == "running":
        raise HTTPException(409, "Wait for the performance to finish, then revise.")
    if not entry["versions"]:
        raise HTTPException(409, "This chunk has no take to revise yet.")
    if len(entry["versions"]) >= MAX_VERSIONS:
        raise HTTPException(409, f"This chunk already has {MAX_VERSIONS} versions. Pick one or perform again.")
    if not req.instruction.strip() and not req.retake:
        raise HTTPException(400, "Describe the change, or ask for a retake.")
    base = entry["lines"][entry["selected"]]
    understood: list[str] = []
    unused: list[str] = []
    line = base
    if req.instruction.strip():
        line, understood, unused = shark.revise(shark.Chunk(**{**_chunk_fields(entry), "line": base}), req.instruction)
        if not understood and not req.retake:
            raise HTTPException(400, "Shark didn't recognise that note. Try words like softer, slower, sad or warm.")
    take = max(v["take"] for v in entry["versions"]) + 1 if req.retake else entry["versions"][entry["selected"]]["take"]
    note = req.instruction.strip() or "retake"
    sem = _busy()
    try:
        with _lock:
            record = _render_version(job, index, line, take, note)
    except HTTPException:
        raise
    except VersionLimit as e:
        raise HTTPException(409, str(e)) from None
    except JobGone:
        raise HTTPException(404, "This performance expired. Perform the script again.") from None
    except Exception as e:
        raise HTTPException(400, _public_error(e)) from None
    finally:
        sem.release()
    entry["state"] = "ready"
    entry.pop("error", None)
    return {"version": record, "understood": understood, "unused": unused, "chunk": _view(job)["chunks"][index]}


def _chunk_fields(entry: dict) -> dict:
    c: shark.Chunk = entry["chunk"]
    return {"index": c.index, "speaker": c.speaker, "voice": c.voice, "text": c.text}


@router.post("/jobs/{job}/chunks/{index}/select")
def select(job: str, index: int, req: Selection):
    entry = _entry(job, index)
    if req.version >= len(entry["versions"]):
        raise HTTPException(404, "No such version.")
    entry["selected"] = req.version
    return _view(job)["chunks"][index]


@router.get("/jobs/{job}/chunks/{index}/{version}.wav")
def chunk_audio(job: str, index: int, version: int):
    entry = _entry(job, index)
    if not 0 <= version < len(entry["versions"]):
        raise HTTPException(404, "No such version.")
    return FileResponse(WORK / job / f"{index}-{version}.wav", media_type="audio/wav")


@router.get("/jobs/{job}/performance.wav")
def performance(job: str):
    j = _job(job)
    if j["status"] == "running":
        raise HTTPException(409, "The performance is still rendering.")
    parts = []
    for i, entry in enumerate(j["chunks"]):
        if entry["selected"] is None:
            continue  # a failed chunk is left out; the page says which
        audio, _ = sf.read(WORK / job / f"{i}-{entry['selected']}.wav", dtype="float32")
        parts.append((audio, entry["plan"]["pause_after"]))
    if not parts:
        raise HTTPException(409, "No chunk rendered successfully.")
    path = WORK / job / "performance.wav"
    sf.write(path, np.clip(shark.assemble(parts), -1, 1), st.SR, subtype="PCM_16")
    return FileResponse(path, media_type="audio/wav", filename="shark-audio-performance.wav")
