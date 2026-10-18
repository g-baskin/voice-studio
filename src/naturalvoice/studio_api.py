"""API routes for /api/studio (registered in server.py)."""
from __future__ import annotations

import io
import json
import logging
import re
import shutil
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Literal

import soundfile as sf
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from . import studio as st

router = APIRouter(prefix="/api/studio")
log = logging.getLogger(__name__)
WORK = Path(tempfile.gettempdir()) / "naturalvoice-studio"
MUSIC_MAX = 200 * 1024 * 1024
MUSIC_EXTS = {".wav", ".flac", ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".aiff", ".aif"}
KEEP_RENDERS = 8
jobs: dict[str, dict] = {}
HEX12 = re.compile(r"^[0-9a-f]{12}$")
HEX32 = re.compile(r"^[0-9a-f]{32}$")

Delivery = Literal["neutral", "warm", "energetic", "calm", "serious", "excited", "soft", "custom"]


class Line(BaseModel):
    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12], pattern=r"^[0-9a-zA-Z_-]{1,40}$")
    text: str = Field(default="", max_length=5000)
    voice: str = "af_heart"
    speaker: str = Field(default="", max_length=60)
    speed: float = Field(1.0, ge=0.5, le=2.0)
    pitch: float = Field(0.0, ge=-4.0, le=4.0)
    volume: float = Field(0.0, ge=-24.0, le=12.0)
    pause: float = Field(0.4, ge=0.0, le=10.0)
    delivery: Delivery = "neutral"
    take: int = Field(0, ge=0, le=2**31 - 1)
    takes: list[int] = Field(default_factory=lambda: [0], max_length=5)
    target: float | None = Field(None, ge=0.5, le=600.0)
    start: float | None = Field(None, ge=0.0, le=86400.0)
    end: float | None = Field(None, ge=0.0, le=86400.0)
    note: str = Field(default="", max_length=200)
    style: dict | None = None

    @field_validator("style")
    @classmethod
    def _style(cls, v):
        if v is None:
            return None
        try:
            return st.validate_style(v)
        except st.StudioError as e:
            raise ValueError(str(e))

    @model_validator(mode="after")
    def _custom(self):
        if self.delivery == "custom" and not self.style:
            self.delivery = "neutral"  # a custom delivery without its style falls back honestly
        return self

    @field_validator("takes")
    @classmethod
    def _takes(cls, v):
        if any(not 0 <= t < 2**31 for t in v):
            raise ValueError("Invalid take.")
        return list(dict.fromkeys(v)) or [0]

    @field_validator("voice")
    @classmethod
    def _voice(cls, v):
        if not st.VOICE_ID.match(v):
            raise ValueError("Invalid voice id.")
        return v


class Project(BaseModel):
    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)
    title: str = Field(default="Untitled project", max_length=120)
    lines: list[Line] = Field(default_factory=list, max_length=st.MAX_LINES)
    dictionary: dict[str, str] = Field(default_factory=dict)
    cast: dict[str, str] = Field(default_factory=dict)
    mode: Literal["sequential", "timed"] = "sequential"

    @field_validator("dictionary")
    @classmethod
    def _dict(cls, d):
        if len(d) > 500:
            raise ValueError("Pronunciation dictionary: 500 entries max.")
        out = {}
        for k, v in d.items():
            k, v = k.strip(), v.strip()
            if not k:
                continue
            if len(k) > 60 or not re.fullmatch(r"[\w'.\- ]+", k):
                raise ValueError(f"Dictionary word {k[:30]!r} must be letters, digits, ' . - or spaces (60 max).")
            if not v or len(v) > 200 or "[" in v or "]" in v:
                raise ValueError(f"Dictionary entry for {k!r} needs a respelling (200 characters max, no brackets).")
            out[k] = v
        return out

    @field_validator("cast")
    @classmethod
    def _cast(cls, d):
        if len(d) > 100 or any(len(k) > 60 or not st.VOICE_ID.match(v) for k, v in d.items()):
            raise ValueError("Invalid cast table.")
        return d

    @model_validator(mode="after")
    def _size(self):
        if sum(len(ln.text) for ln in self.lines) > st.MAX_CHARS:
            raise ValueError(f"Script is longer than {st.MAX_CHARS:,} characters.")
        return self


class RenderRequest(BaseModel):
    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)
    project: Project
    target: Literal["youtube", "podcast", "broadcast", "acx", "raw"] = "podcast"
    sample_rate: Literal[24000, 44100, 48000] = 24000
    format: Literal["wav", "flac", "mp3"] = "wav"
    stems: bool = False
    line_clips: bool = False
    captions: bool = True
    polish: bool = False
    stop_on_error: bool = False
    music_id: str | None = Field(None, pattern=r"^[0-9a-f]{32}$")
    music_level_db: float = Field(-18.0, ge=-40.0, le=0.0)
    music_loop: bool = True
    duck: bool = True
    duck_db: float = Field(12.0, ge=0.0, le=30.0)
    attack_ms: float = Field(80.0, ge=5.0, le=1000.0)
    release_ms: float = Field(400.0, ge=20.0, le=3000.0)
    fade_in: float = Field(1.0, ge=0.0, le=10.0)
    fade_out: float = Field(2.0, ge=0.0, le=10.0)
    target_duration: float | None = Field(None, ge=1.0, le=3600.0)
    room_tone: bool | None = None
    video_id: str | None = Field(None, pattern=r"^[0-9a-f]{32}$")
    video_mode: Literal["replace", "duck"] = "replace"
    video_level_db: float = Field(-6.0, ge=-40.0, le=6.0)
    video_subs: bool = True


class PreviewRequest(BaseModel):
    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)
    line: Line
    dictionary: dict[str, str] = Field(default_factory=dict)
    polish: bool = False

    @field_validator("dictionary")
    @classmethod
    def _d(cls, d):
        return Project._dict(d)


class ParseRequest(BaseModel):
    text: str = Field(max_length=st.MAX_CHARS)
    cast: dict[str, str] = Field(default_factory=dict)


def _busy():
    from .server import processing

    if not processing.acquire(blocking=False):
        raise HTTPException(429, "Another render or file is processing. Wait for it to finish, then retry.")
    return processing


# --------------------------------------------------------------------------- info, parsing, preview
@router.get("/presets")
def presets():
    return {"delivery": {k: {"label": v["label"], "does": v["does"]} for k, v in st.DELIVERY.items()},
            "targets": {k: v["label"] for k, v in st.TARGETS.items()},
            "limits": {"lines": st.MAX_LINES, "chars": st.MAX_CHARS, "music_mb": MUSIC_MAX // 2**20}}


@router.post("/parse")
def parse(req: ParseRequest):
    try:
        res = st.parse_script(req.text, req.cast)
    except st.StudioError as e:
        raise HTTPException(400, str(e))
    res["warnings"] = st.lint_project(res)
    return res


@router.post("/lint")
def lint(project: Project):
    return {"warnings": st.lint_project(project.model_dump())}


@router.post("/preview")
def preview(req: PreviewRequest):
    if not req.line.text.strip():
        raise HTTPException(400, "This line has no text to preview.")
    key = st.line_key(req.line.model_dump(), req.dictionary, req.polish)
    cached = key in st._cache
    sem = None if cached else _busy()
    try:
        x, _ = st.render_line(req.line.model_dump(), req.dictionary, req.polish)
    except (RuntimeError, ValueError, KeyError) as e:
        raise HTTPException(400, str(e).strip("'\""))
    finally:
        if sem:
            sem.release()
    buf = io.BytesIO()
    sf.write(buf, x.clip(-1, 1), st.SR, format="WAV", subtype="PCM_16")
    return Response(buf.getvalue(), media_type="audio/wav", headers={"X-Cache": "hit" if cached else "miss"})


# --------------------------------------------------------------------------- custom styles
class StyleIn(BaseModel):
    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)
    name: str = Field(min_length=1, max_length=60)
    line: Line | None = None  # capture from a line's current settings
    style: dict | None = None  # or give the values directly


_styles_lock = threading.Lock()


@router.get("/styles")
def list_styles():
    return {"styles": st.load_styles(), "max": st.MAX_STYLES}


@router.post("/styles", status_code=201)
def save_style(body: StyleIn):
    try:
        if body.line is not None:
            rec = st.style_from_line(body.line.model_dump(), body.name)
        elif body.style is not None:
            rec = st.validate_style({**{k: v for k, v in body.style.items() if k != "id"}, "name": body.name})
        else:
            raise HTTPException(400, "Send a line to capture, or style values.")
    except st.StudioError as e:
        raise HTTPException(400, str(e))
    rec.pop("id", None)
    with _styles_lock:
        styles = st.load_styles()
        if len(styles) >= st.MAX_STYLES:
            raise HTTPException(400, f"You have {st.MAX_STYLES} styles, the maximum. Delete one first.")
        rec["id"] = uuid.uuid4().hex[:12]
        styles.append(rec)
        st.save_styles(styles)
    return rec


@router.delete("/styles/{sid}")
def delete_style(sid: str):
    if not HEX12.match(sid):
        raise HTTPException(400, "Invalid style id.")
    with _styles_lock:
        styles = st.load_styles()
        keep = [x for x in styles if x["id"] != sid]
        if len(keep) == len(styles):
            raise HTTPException(404, "Style not found.")
        st.save_styles(keep)
    return {"deleted": sid}


# --------------------------------------------------------------------------- director's notes
class NoteIn(BaseModel):
    note: str = Field(max_length=200)
    line: Line


@router.post("/note")
def understand_note(body: NoteIn):
    ln = body.line.model_dump()
    tags = st.clone_emotion_tags() if ln["voice"].startswith("clone:") else []
    return st.parse_note(body.note, ln, tags)


# --------------------------------------------------------------------------- music upload
@router.post("/music")
async def upload_music(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in MUSIC_EXTS:
        raise HTTPException(400, "Music must be WAV, FLAC, MP3, M4A, AAC, OGG, Opus or AIFF.")
    d = WORK / "music"
    d.mkdir(parents=True, exist_ok=True)
    for old in d.iterdir():  # uploads are session scratch: drop anything older than a day
        if time.time() - old.stat().st_mtime > 86400:
            old.unlink(missing_ok=True)
    mid = uuid.uuid4().hex
    path = d / f"{mid}{suffix}"
    size = 0
    try:
        with path.open("wb") as fh:
            while chunk := await file.read(1 << 20):
                size += len(chunk)
                if size > MUSIC_MAX:
                    raise HTTPException(413, "Music file too large (200 MB max).")
                fh.write(chunk)
        if not size:
            raise HTTPException(400, "The music file is empty.")
        from . import audio as aio
        try:
            data, sr = aio.load(path)
        except Exception:
            raise HTTPException(400, "Could not read that music file. Try WAV or MP3.")
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()
    return {"music_id": mid, "name": Path(file.filename).name[:120], "seconds": round(len(data) / sr, 1)}


VIDEO_MAX = 2 * 1024 ** 3


def _scratch(kind: str) -> Path:
    d = WORK / kind
    d.mkdir(parents=True, exist_ok=True)
    for old in d.iterdir():  # session scratch: drop anything older than a day
        if time.time() - old.stat().st_mtime > 86400:
            old.unlink(missing_ok=True)
    return d


def _upload_path(kind: str, uid_: str, msg: str) -> Path:
    for p in (WORK / kind).glob(f"{uid_}.*"):
        return p
    raise HTTPException(400, msg)


async def _stream(file: UploadFile, path: Path, limit: int, too_big: str) -> int:
    size = 0
    with path.open("wb") as fh:
        while chunk := await file.read(4 << 20):
            size += len(chunk)
            if size > limit:
                raise HTTPException(413, too_big)
            fh.write(chunk)
    if not size:
        raise HTTPException(400, "The file is empty.")
    return size


@router.post("/video")
async def upload_video(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in st.VIDEO_EXTS:
        raise HTTPException(400, "Video must be MP4, MOV, WebM or MKV.")
    vid = uuid.uuid4().hex
    path = _scratch("video") / f"{vid}{suffix}"
    try:
        await _stream(file, path, VIDEO_MAX, "Video too large (2 GB max).")
        streams = st.probe_streams(path)
        if not streams["video"]:
            raise HTTPException(400, "That file has no video picture. Use the music bed for audio-only files.")
        seconds = st.probe_duration(path)
    except st.StudioError as e:
        path.unlink(missing_ok=True)
        raise HTTPException(400, str(e))
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()
    return {"video_id": vid, "name": Path(file.filename).name[:120], "seconds": round(seconds, 2),
            "has_audio": streams["audio"]}


@router.post("/subtitles")
async def import_subtitles(file: UploadFile = File(...), voice: str = "af_heart"):
    if Path(file.filename or "").suffix.lower() not in {".srt", ".vtt"}:
        raise HTTPException(400, "Subtitles must be an .srt or .vtt file.")
    if not st.VOICE_ID.match(voice):
        raise HTTPException(400, "Invalid voice id.")
    data = await file.read(st.MAX_SUB_BYTES + 1)
    await file.close()
    if len(data) > st.MAX_SUB_BYTES:
        raise HTTPException(413, "Subtitle file too large (2 MB max).")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    try:
        return st.parse_subtitles(text, voice)
    except st.StudioError as e:
        raise HTTPException(400, str(e))


def _music_path(mid: str) -> Path:
    for p in (WORK / "music").glob(f"{mid}.*"):
        return p
    raise HTTPException(400, "Music upload expired. Upload it again.")


# --------------------------------------------------------------------------- render jobs
def _prune():
    done = [k for k, j in jobs.items() if j["status"] != "running"]
    for k in done[:-KEEP_RENDERS]:
        shutil.rmtree(WORK / "renders" / k, ignore_errors=True)
        jobs.pop(k, None)


@router.post("/render")
def render(req: RenderRequest):
    project = req.project.model_dump()
    if not any(ln["text"].strip() for ln in project["lines"]):
        raise HTTPException(400, "Add at least one line with text before rendering.")
    music = _music_path(req.music_id) if req.music_id else None
    video = _upload_path("video", req.video_id, "Video upload expired. Upload it again.") if req.video_id else None
    sem = _busy()
    _prune()
    job = uuid.uuid4().hex
    out = WORK / "renders" / job
    cancel = threading.Event()
    jobs[job] = {"status": "running", "step": "Starting", "progress": 0.0, "title": project["title"],
                 "created": time.time(), "cancel": cancel}
    opts = st.RenderOptions(target=req.target, sample_rate=req.sample_rate, format=req.format, stems=req.stems,
                            line_clips=req.line_clips, captions=req.captions, polish=req.polish,
                            stop_on_error=req.stop_on_error, music=music, music_level_db=req.music_level_db,
                            music_loop=req.music_loop, duck=req.duck, duck_db=req.duck_db, attack_ms=req.attack_ms,
                            release_ms=req.release_ms, fade_in=req.fade_in, fade_out=req.fade_out,
                            target_duration=req.target_duration, room_tone=req.room_tone,
                            video=video, video_mode=req.video_mode, video_level_db=req.video_level_db,
                            video_subs=req.video_subs)

    def run():
        try:
            res = st.render_project(project, opts, out, lambda s, f: jobs[job].update(step=s, progress=round(f, 3)), cancel)
            jobs[job].update(status="done", progress=1.0, step="Done", result=res)
        except st.Cancelled:
            jobs[job].update(status="cancelled", step="Cancelled")
            shutil.rmtree(out, ignore_errors=True)
        except st.StudioError as e:
            jobs[job].update(status="error", error=str(e))
            shutil.rmtree(out, ignore_errors=True)
        except Exception:
            log.exception("Studio render failed")
            jobs[job].update(status="error", error="The render failed. Try fewer lines or a different voice, then retry.")
            shutil.rmtree(out, ignore_errors=True)
        finally:
            sem.release()

    threading.Thread(target=run, daemon=True).start()
    return {"job": job}


def _job(job: str) -> dict:
    j = jobs.get(job) if HEX32.match(job) else None
    if not j:
        raise HTTPException(404, "No such render.")
    return j


@router.get("/render/{job}")
def render_status(job: str):
    return {k: v for k, v in _job(job).items() if k != "cancel"}


@router.post("/render/{job}/cancel")
def render_cancel(job: str):
    j = _job(job)
    if j["status"] == "running":
        j["cancel"].set()
        j["step"] = "Cancelling after the current line"
    return {"status": j["status"]}


@router.get("/renders")
def renders():
    return {"renders": [{"job": k, "title": j["title"], "status": j["status"], "created": j["created"],
                         "duration": j.get("result", {}).get("duration")} for k, j in reversed(jobs.items())]}


@router.get("/render/{job}/file/{name}")
def render_file(job: str, name: str):
    j = _job(job)
    res = j.get("result")
    if j["status"] != "done" or not res:
        raise HTTPException(404, "Render not finished.")
    allowed = {f["name"] for f in res["files"]} | {res["zip"]}
    if name not in allowed:
        raise HTTPException(404, "No such file.")
    path = WORK / "renders" / job / name
    if not path.exists():
        raise HTTPException(404, "File expired.")
    types = {".wav": "audio/wav", ".flac": "audio/flac", ".mp3": "audio/mpeg", ".srt": "text/plain",
             ".vtt": "text/vtt", ".json": "application/json", ".zip": "application/zip"}
    return FileResponse(path, media_type=types.get(path.suffix, "application/octet-stream"), filename=name)


# --------------------------------------------------------------------------- projects
def _ppath(pid: str) -> Path:
    if not HEX12.match(pid):
        raise HTTPException(400, "Invalid project id.")
    return st.projects_dir() / f"{pid}.json"


def _load(pid: str) -> dict:
    p = _ppath(pid)
    if not p.exists():
        raise HTTPException(404, "Project not found.")
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        proj = Project.model_validate(raw.get("project", raw)).model_dump()
    except (OSError, ValueError, ValidationError, AttributeError):
        raise HTTPException(422, "This project file is damaged or from an incompatible version.")
    return {"id": pid, "updated": raw.get("updated", 0) if isinstance(raw, dict) else 0, "project": proj}


def _save(pid: str, project: dict) -> dict:
    d = st.projects_dir()
    d.mkdir(parents=True, exist_ok=True)
    rec = {"id": pid, "updated": time.time(), "project": project}
    tmp = d / f".{pid}.tmp"
    tmp.write_text(json.dumps(rec, indent=1), encoding="utf-8")
    tmp.replace(_ppath(pid))
    return rec


@router.get("/projects")
def list_projects():
    d = st.projects_dir()
    out = []
    for p in sorted(d.glob("*.json")) if d.exists() else []:
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            proj = raw["project"]
            out.append({"id": p.stem, "title": str(proj.get("title", ""))[:120], "lines": len(proj.get("lines", [])),
                        "updated": raw.get("updated", 0)})
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            out.append({"id": p.stem, "title": "(damaged project file)", "lines": 0, "updated": 0, "damaged": True})
    return {"projects": sorted(out, key=lambda r: r["updated"], reverse=True)}


@router.post("/projects")
def create_project(project: Project):
    return _save(uuid.uuid4().hex[:12], project.model_dump())


@router.get("/projects/{pid}")
def get_project(pid: str):
    return _load(pid)


@router.put("/projects/{pid}")
def update_project(pid: str, project: Project):
    _ppath(pid)
    return _save(pid, project.model_dump())


@router.post("/projects/{pid}/duplicate")
def duplicate_project(pid: str):
    proj = _load(pid)["project"]
    proj["title"] = (proj["title"] + " (copy)")[:120]
    return _save(uuid.uuid4().hex[:12], proj)


@router.delete("/projects/{pid}")
def delete_project(pid: str):
    p = _ppath(pid)
    if not p.exists():
        raise HTTPException(404, "Project not found.")
    p.unlink()
    return {"deleted": pid}
