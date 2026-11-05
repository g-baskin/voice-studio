"""HTTP API for the Editor page: media bin, sequences, video export and Premiere XML."""

from __future__ import annotations

import queue
import re
import shutil
import tempfile
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import editor as ed

router = APIRouter(prefix="/api/editor")
EXPORTS = Path(tempfile.gettempdir()) / "naturalvoice-editor"
KEEP_EXPORTS = 5
KEEP_ANALYSES = 20
MAX_BATCH = 50
_SAFE_NAME = re.compile(r"[^A-Za-z0-9 _.-]+")


class Ingest:
    """Prepares uploads one at a time, sharing the app's single processing slot."""

    def __init__(self) -> None:
        self.jobs: queue.Queue[str] = queue.Queue()
        self.waiting: set[str] = set()
        self.lock = threading.Lock()
        self.thread: threading.Thread | None = None

    def add(self, media_id: str) -> None:
        with self.lock:
            if media_id in self.waiting:
                return
            self.waiting.add(media_id)
            self.jobs.put(media_id)
            if self.thread is None or not self.thread.is_alive():
                self.thread = threading.Thread(target=self._work, name="editor-ingest", daemon=True)
                self.thread.start()

    def resume(self, records: list[dict]) -> None:
        # Uploads interrupted by a server restart are prepared again rather than left spinning.
        for record in records:
            if record["status"] == "processing" and record["id"] not in self.waiting:
                self.add(record["id"])

    def _work(self) -> None:
        from .server import processing

        while True:
            try:
                media_id = self.jobs.get(timeout=5)
            except queue.Empty:
                with self.lock:
                    if self.jobs.empty():
                        self.thread = None
                        return
                continue
            with processing:
                try:
                    ed.process_media(media_id)
                except ed.EditorError as exc:
                    self._fail(media_id, str(exc))
                except Exception:  # an unreadable file must not stop later uploads
                    self._fail(media_id, "Could not prepare that file.")
                finally:
                    with self.lock:
                        self.waiting.discard(media_id)

    @staticmethod
    def _fail(media_id: str, message: str) -> None:
        try:
            record = ed.media_record(media_id)
        except ed.EditorError:
            return
        record.update(status="error", error=message)
        ed.save_media(record)


ingest = Ingest()
exports: dict[str, dict] = {}
analyses: dict[str, dict] = {}


def _bad(exc: ed.EditorError, status: int = 400) -> HTTPException:
    return HTTPException(status, str(exc))


# --------------------------------------------------------------------------- media bin
@router.get("/media")
def media_list() -> list[dict]:
    records = ed.list_media()
    ingest.resume(records)
    return records


@router.post("/media", status_code=201)
async def media_upload(request: Request, name: str) -> dict:
    try:
        length = int(request.headers.get("content-length", "-1"))
    except ValueError:
        length = -1
    if length <= 0:
        raise HTTPException(411 if length < 0 else 400, "Send the file with its size.")
    if length > ed.MAX_BYTES:
        raise HTTPException(413, "File too large (2 GB max).")
    try:
        record, path = ed.new_media(name)
    except ed.EditorError as exc:
        raise _bad(exc) from None
    if shutil.disk_usage(path.parent).free < length + 1024**3:
        shutil.rmtree(path.parent)
        raise HTTPException(507, "Not enough free disk space for that file.")
    size = 0
    try:
        with path.open("wb") as stream:
            async for chunk in request.stream():
                size += len(chunk)
                if size > length or size > ed.MAX_BYTES:
                    raise HTTPException(413, "The upload is larger than it said it would be.")
                stream.write(chunk)
        if size != length:
            raise HTTPException(400, "The upload was interrupted. Try again.")
    except BaseException:
        shutil.rmtree(path.parent, ignore_errors=True)
        raise
    record.update(status="processing", size=size)
    ed.save_media(record)
    ingest.add(record["id"])
    return record


def _media(media_id: str) -> dict:
    try:
        return ed.media_record(media_id)
    except ed.EditorError as exc:
        raise _bad(exc, 404) from None


@router.get("/media/{media_id}")
def media_get(media_id: str) -> dict:
    return _media(media_id)


@router.get("/media/{media_id}/proxy")
def media_proxy(media_id: str) -> FileResponse:
    _media(media_id)
    try:
        path = ed.proxy_file(media_id)
    except ed.EditorError as exc:
        raise _bad(exc, 409) from None
    return FileResponse(path, headers={"Cache-Control": "private, max-age=86400"})


@router.get("/media/{media_id}/thumbs")
def media_thumbs(media_id: str) -> FileResponse:
    _media(media_id)
    path = ed.media_dir(media_id) / "thumbs.jpg"
    if not path.is_file():
        raise HTTPException(404, "No filmstrip for that media.")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


@router.get("/media/{media_id}/peaks")
def media_peaks(media_id: str) -> FileResponse:
    _media(media_id)
    path = ed.media_dir(media_id) / "peaks.json"
    if not path.is_file():
        raise HTTPException(404, "No waveform for that media.")
    return FileResponse(path, media_type="application/json", headers={"Cache-Control": "private, max-age=86400"})


@router.delete("/media/{media_id}", status_code=204)
def media_delete(media_id: str) -> Response:
    record = _media(media_id)
    if record["status"] == "processing":
        raise HTTPException(409, "That file is still being prepared. Wait, then remove it.")
    # A running analysis would write its result back into the removed folder.
    if any(j["media"] == media_id and j["status"] == "running" for j in analyses.values()):
        raise HTTPException(409, "That file is being analysed. Cancel or wait, then remove it.")
    try:
        ed.delete_media(media_id)
    except ed.EditorError as exc:
        raise _bad(exc, 409) from None
    return Response(status_code=204)


# --------------------------------------------------------------------------- clip analysis
class AnalysisRequest(BaseModel):
    kind: Literal["silence", "scenes", "moments"]
    noise_db: float = Field(-40.0, ge=-80, le=-10)
    min_seconds: float = Field(0.5, ge=0.1, le=10)
    threshold: float = Field(0.3, ge=0.05, le=0.95)
    min_length: float = Field(15.0, ge=1, le=600)
    max_length: float = Field(60.0, ge=1, le=600)
    count: int = Field(10, ge=1, le=30)

    @model_validator(mode="after")
    def _lengths(self) -> AnalysisRequest:
        if self.max_length < self.min_length:
            raise ValueError("The longest moment must be at least as long as the shortest.")
        return self

    def params(self) -> dict[str, float]:
        if self.kind == "silence":
            return {"noise_db": self.noise_db, "min_seconds": self.min_seconds}
        if self.kind == "scenes":
            return {"threshold": self.threshold}
        return {"min_length": self.min_length, "max_length": self.max_length, "count": self.count}


def _forget_analyses() -> None:
    # Results stay cached beside the media; only the in-memory job records are dropped.
    done = sorted((k for k, j in analyses.items() if j["status"] != "running"), key=lambda k: analyses[k]["created"])
    for key in done[: max(0, len(done) - KEEP_ANALYSES)]:
        analyses.pop(key, None)


def _analysis(media_id: str, key: str) -> dict:
    job = analyses.get(key)
    if job is None or job["media"] != media_id:
        raise HTTPException(404, "That analysis has expired. Run it again.")
    return job


@router.post("/media/{media_id}/analysis", status_code=202)
def analysis_start(media_id: str, body: AnalysisRequest) -> dict:
    from .server import processing

    record = _media(media_id)
    if record["status"] != "ready":
        raise HTTPException(409, "That file is not ready yet. Wait for it to finish preparing.")
    if record["kind"] == "image" or not record.get("duration"):
        raise HTTPException(400, "Only video and audio can be analysed.")
    _forget_analyses()
    key = uuid.uuid4().hex
    job = {"id": key, "media": media_id, "kind": body.kind, "status": "running", "progress": 0.0}
    job |= {"error": None, "created": time.time(), "result": None}
    params = body.params()
    try:
        cached = ed.analysis_cached(media_id, body.kind, params)
    except ed.EditorError as exc:
        raise _bad(exc) from None
    if cached is not None:
        analyses[key] = job | {"status": "done", "progress": 1.0, "result": cached}
        return _public(analyses[key])
    if not processing.acquire(blocking=False):
        raise HTTPException(429, "Another export or file is processing. Wait for it to finish, then retry.")
    cancel = threading.Event()
    analyses[key] = job | {"cancel": cancel}

    def run() -> None:
        final: dict = {}
        try:
            result = ed.analyse(
                media_id, body.kind, params, lambda f: analyses[key].update(progress=round(f, 3)), cancel
            )
            final = {"status": "done", "progress": 1.0, "result": result}
        except ed.Cancelled:
            final = {"status": "cancelled"}
        except ed.EditorError as exc:
            final = {"status": "error", "error": str(exc)}
        except Exception:
            final = {"status": "error", "error": "The analysis stopped unexpectedly."}
        finally:
            # Free the slot before reporting, so a client that sees the result can start the next job.
            processing.release()
            analyses[key].update(final)

    threading.Thread(target=run, name=f"editor-analysis-{key[:8]}", daemon=True).start()
    return _public(analyses[key])


@router.get("/media/{media_id}/analysis/{key}")
def analysis_status(media_id: str, key: str) -> dict:
    return _public(_analysis(media_id, key))


@router.post("/media/{media_id}/analysis/{key}/cancel")
def analysis_cancel(media_id: str, key: str) -> dict:
    job = _analysis(media_id, key)
    if "cancel" in job:
        job["cancel"].set()
    return _public(job)


# --------------------------------------------------------------------------- sequences
@router.get("/sequences")
def sequence_list() -> list[dict]:
    return ed.list_sequences()


@router.post("/sequences", status_code=201)
def sequence_create(sequence: ed.Sequence) -> dict:
    return ed.save_sequence(sequence)


@router.get("/sequences/{sequence_id}")
def sequence_get(sequence_id: str) -> dict:
    try:
        return ed.read_sequence(sequence_id)
    except ed.EditorError as exc:
        raise _bad(exc, 404) from None


@router.put("/sequences/{sequence_id}")
def sequence_save(sequence_id: str, sequence: ed.Sequence) -> dict:
    try:
        return ed.save_sequence(sequence, sequence_id)
    except ed.EditorError as exc:
        raise _bad(exc, 404) from None


@router.delete("/sequences/{sequence_id}", status_code=204)
def sequence_delete(sequence_id: str) -> Response:
    try:
        ed.delete_sequence(sequence_id)
    except ed.EditorError as exc:
        raise _bad(exc, 404) from None
    return Response(status_code=204)


def _filename(name: str, suffix: str) -> str:
    return (_SAFE_NAME.sub("", name).strip() or "sequence")[:60] + suffix


@router.get("/sequences/{sequence_id}/premiere.xml")
def sequence_premiere(sequence_id: str) -> Response:
    try:
        sequence = ed.Sequence.model_validate(ed.read_sequence(sequence_id))
        xml = ed.premiere_xml(sequence, ed.media_for(sequence))
    except ed.EditorError as exc:
        raise _bad(exc, 404 if "no longer exists" in str(exc) else 400) from None
    name = _filename(sequence.name, ".xml")
    return Response(
        xml, media_type="application/xml", headers={"Content-Disposition": f'attachment; filename="{name}"'}
    )


# --------------------------------------------------------------------------- export jobs
class ExportRange(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    start: float = Field(alias="in", ge=0, le=ed.MAX_SECONDS)
    end: float = Field(alias="out", ge=0, le=ed.MAX_SECONDS)
    label: str = Field("", max_length=60)

    @model_validator(mode="after")
    def _order(self) -> ExportRange:
        if self.end <= self.start:
            raise ValueError("Each range must end after it starts.")
        return self


class ExportRequest(BaseModel):
    sequence: ed.Sequence
    in_out: bool = False
    quality: str = Field("standard", pattern="^(high|standard|draft)$")
    ranges: list[ExportRange] | None = Field(None, min_length=1, max_length=MAX_BATCH)

    def parts(self) -> list[tuple[ed.Sequence, bool, str]]:
        """Each file to render: its sequence, whether to use its in/out range, and its file name."""
        if not self.ranges:
            return [(self.sequence, self.in_out, _filename(self.sequence.name, ".mp4"))]
        base = self.sequence.model_dump()
        stem = _filename(self.sequence.name, "")[:40]
        out = []
        for n, r in enumerate(self.ranges, 1):
            seq = ed.Sequence.model_validate(base | {"range_in": r.start, "range_out": r.end})
            label = _SAFE_NAME.sub("", r.label).strip()[:40]
            out.append((seq, True, f"{stem}-{n:02d}" + (f"-{label}" if label else "") + ".mp4"))
        return out


def _prune() -> None:
    done = sorted((k for k, j in exports.items() if j["status"] != "running"), key=lambda k: exports[k]["created"])
    for key in done[: max(0, len(done) - KEEP_EXPORTS)]:
        shutil.rmtree(EXPORTS / key, ignore_errors=True)
        exports.pop(key, None)


def _public(job: dict) -> dict:
    return {k: v for k, v in job.items() if k not in {"cancel", "path", "paths"}}


@router.post("/exports", status_code=202)
def export_start(body: ExportRequest) -> dict:
    from .server import processing

    try:
        parts = body.parts()
        media = ed.media_for(body.sequence)
        for n, (seq, in_out, _) in enumerate(parts, 1):
            try:
                ed.build_command(seq, media, EXPORTS / "check.mp4", in_out)
            except ed.EditorError as exc:
                raise ed.EditorError(f"Range {n}: {exc}" if body.ranges else str(exc)) from None
    except ed.EditorError as exc:
        raise _bad(exc) from None
    if not processing.acquire(blocking=False):
        raise HTTPException(429, "Another export or file is processing. Wait for it to finish, then retry.")
    _prune()
    key = uuid.uuid4().hex
    cancel = threading.Event()
    paths = [EXPORTS / key / name for _, _, name in parts]
    exports[key] = {"id": key, "status": "running", "progress": 0.0, "error": None, "created": time.time()}
    exports[key] |= {"name": paths[0].name, "files": [p.name for p in paths], "done": 0}
    exports[key] |= {"cancel": cancel, "path": paths[0], "paths": paths}

    def run() -> None:
        total = len(parts)
        final: dict = {}

        def report(i: int) -> Callable[[float], None]:
            return lambda f: exports[key].update(progress=round((i + f) / total, 3))

        try:
            # One file at a time; cancelling stops the rest of the batch too.
            for i, ((seq, in_out, _), out) in enumerate(zip(parts, paths, strict=True)):
                ed.render(seq, out, in_out, body.quality, report(i), cancel)
                exports[key].update(done=i + 1)
            final = {"status": "done", "progress": 1.0}
        except ed.Cancelled:
            final = {"status": "cancelled"}
        except ed.EditorError as exc:
            final = {"status": "error", "error": str(exc)}
        except Exception:
            final = {"status": "error", "error": "The export stopped unexpectedly."}
        finally:
            # Free the slot before reporting, so a client that sees the result can start the next job.
            processing.release()
            exports[key].update(final)

    threading.Thread(target=run, name=f"editor-export-{key[:8]}", daemon=True).start()
    return _public(exports[key])


def _job(key: str) -> dict:
    job = exports.get(key)
    if job is None:
        raise HTTPException(404, "That export has expired. Export again.")
    return job


@router.get("/exports/{key}")
def export_status(key: str) -> dict:
    return _public(_job(key))


@router.post("/exports/{key}/cancel")
def export_cancel(key: str) -> dict:
    job = _job(key)
    job["cancel"].set()
    return _public(job)


@router.get("/exports/{key}/file")
def export_file(key: str, index: int = 0) -> FileResponse:
    job = _job(key)
    paths: list[Path] = job["paths"]
    if not 0 <= index < len(paths):
        raise HTTPException(404, "That export has no such file.")
    path = paths[index]
    if index >= job["done"] or not path.is_file():
        raise HTTPException(409, "That export is not finished.")
    return FileResponse(path, media_type="video/mp4", filename=path.name)
