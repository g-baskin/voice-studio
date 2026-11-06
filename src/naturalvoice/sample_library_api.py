"""Loopback-only API for reviewed, permission-based voice sample collections."""

from __future__ import annotations

import os
from ipaddress import ip_address
import shutil
import threading
import time
import uuid
from contextlib import contextmanager
from collections.abc import Iterator

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from starlette.formparsers import MultiPartException
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from pydantic import BaseModel, Field

from . import sample_library as library


def local_request(request: Request) -> None:
    try:
        local_peer = request.client is not None and ip_address(request.client.host).is_loopback
    except ValueError:
        local_peer = False
    if not local_peer or request.url.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise HTTPException(403, "Sample collections are only available through localhost.")
    origin = request.headers.get("origin")
    if origin and origin != f"{request.url.scheme}://{request.url.netloc}":
        raise HTTPException(403, "Open this page from the local Shark Audio app.")
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, "Cross-site requests are not allowed.")


class SampleUploadLimit:
    """Bound multipart bytes before Starlette can spool an entire oversized movie."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] != "/api/samples/sources" or scope["method"] != "POST":
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        try:
            local_request(request)
        except HTTPException as exc:
            await JSONResponse({"detail": exc.detail}, status_code=exc.status_code)(scope, receive, send)
            return
        limit = library.MAX_BYTES + 64 * 1024  # bounded multipart headers and form fields
        try:
            length = int(request.headers.get("content-length", "0"))
        except ValueError:
            length = -1
        if length < 0 or length > limit:
            await JSONResponse({"detail": "Upload is too large (250 MB max)."}, status_code=413)(scope, receive, send)
            return
        received = 0
        exceeded = False

        async def bounded_receive() -> Message:
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    exceeded = True
                    # Starlette closes partially spooled files when its multipart parser sees this exception.
                    raise MultiPartException("Upload is too large (250 MB max).")
            return message

        async def bounded_send(message: Message) -> None:
            if exceeded and message["type"] == "http.response.start":
                message = {**message, "status": 413}
            await send(message)

        await self.app(scope, bounded_receive, bounded_send)


router = APIRouter(prefix="/api/samples", dependencies=[Depends(local_request)])


@contextmanager
def errors() -> Iterator[None]:
    try:
        yield
    except KeyError:
        raise HTTPException(404, "Library item not found.") from None
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    except OSError:
        raise HTTPException(507, "Could not read or save library files. Check disk space and permissions.") from None


def processing():
    from .server import processing as lock

    return lock


def launch(key: str) -> None:
    def run() -> None:
        try:
            library.process_source(key)
        finally:
            processing().release()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()


@router.get("")
def catalog():
    with errors():
        return {
            "installed": library.installed(),
            "people": library.records("people"),
            "sources": [library.public_source(s) for s in library.records("sources")],
            "setup": "Run scripts/setup_media_engine.sh in the app folder.",
        }


@router.post("/sources", status_code=202)
async def import_source(
    file: UploadFile | None = File(None),
    url: str = Form(""),
    start: float = Form(0),
    seconds: float = Form(30),
    separate: bool = Form(False),
    speakers: int = Form(0),
    consent: bool = Form(False),
):
    folder = None
    acquired = False
    try:
        with errors():
            if not consent:
                raise ValueError(
                    "Confirm that you have permission to process this recording and clone its selected voices."
                )
            if bool(file and file.filename) == bool(url.strip()):
                raise ValueError("Choose a file or a YouTube URL, not both.")
            library.validate_window(start, seconds)
            if not 0 <= speakers <= 16:
                raise ValueError("Speaker count must be 0 (automatic) to 16.")
            url = library.youtube_url(url) if url.strip() else ""
            suffix = ""
            if file:
                from pathlib import Path

                suffix = Path(file.filename or "").suffix.lower()
                if suffix not in library.EXTS:
                    raise ValueError("Unsupported file. Choose an audio or video recording.")
            if not library.installed():
                raise HTTPException(503, "Install the local media engine with scripts/setup_media_engine.sh first.")
            if not processing().acquire(blocking=False):
                raise HTTPException(429, "Another audio job is running. Wait, then retry.")
            acquired = True
            library.capacity()
            key = uuid.uuid4().hex
            folder = library.location("sources", key)
            folder.mkdir(parents=True)
            if file:
                size = 0
                with (folder / f"input{suffix}").open("wb") as stream:
                    while chunk := await file.read(1 << 20):
                        size += len(chunk)
                        if size > library.MAX_BYTES:
                            raise HTTPException(
                                413, "Upload is too large (250 MB max). Trim the movie externally first."
                            )
                        stream.write(chunk)
                if not size:
                    raise ValueError("The uploaded file is empty.")
            record = {
                "id": key,
                "name": (file.filename or "Recording")[:200] if file else url,
                "input": f"input{suffix}" if file else "",
                "url": url,
                "start": start,
                "seconds": seconds,
                "separate": separate,
                "speakers": speakers,
                "consent": True,
                "created": time.time(),
                "status": "running",
                "step": "Queued locally",
                "pid": os.getpid(),
            }
            library.atomic_json(folder / "record.json", record)
            launch(key)
            acquired = False  # the worker now owns release
            return {"id": key}
    except BaseException:
        if folder is not None and acquired:
            shutil.rmtree(folder, ignore_errors=True)  # only this unaccepted upload
        raise
    finally:
        if acquired:
            processing().release()
        if file is not None:
            await file.close()


@router.get("/sources/{key}")
def source(key: str):
    with errors():
        return library.public_source(library.read("sources", key))


@router.post("/sources/{key}/retry", status_code=202)
def retry(key: str):
    with errors():
        record = library.read("sources", key)
        if library.public_source(record)["status"] != "error":
            raise ValueError("Only failed or interrupted imports can be retried.")
        if not library.installed():
            raise HTTPException(503, "Install the local media engine first.")
        if not processing().acquire(blocking=False):
            raise HTTPException(429, "Another audio job is running. Wait, then retry.")
        try:
            library.capacity(100 * 1024**2)
            record.update(status="running", step="Retrying", pid=os.getpid())
            record.pop("error", None)
            library.atomic_json(library.location("sources", key) / "record.json", record)
            launch(key)
        except BaseException:
            processing().release()
            raise
        return {"id": key}


@router.get("/sources/{key}/audio/{kind}")
def source_audio(key: str, kind: str):
    with errors():
        record = library.read("sources", key)
        if record["status"] != "done" or kind not in {"original", "dialogue"}:
            raise HTTPException(404, "Completed audio not found.")
        return FileResponse(library.location("sources", key) / f"{kind}.wav", media_type="audio/wav")


class Person(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    consent: bool = False


@router.post("/people", status_code=201)
def create_person(body: Person):
    with errors():
        return library.create_person(body.name, body.consent)


@router.get("/people/{key}")
def person(key: str):
    with errors():
        record = library.read("people", key)
        return {
            **record,
            "samples": [s for s in library.records("samples") if s["person"] == key],
            "versions": library.versions(key),
        }


class Sample(BaseModel):
    source: str = Field(pattern=r"^[0-9a-f]{32}$")
    start: float = Field(ge=0, le=120, allow_inf_nan=False)
    end: float = Field(gt=0, le=121, allow_inf_nan=False)
    cleaned: bool = True
    consent: bool = False


@router.post("/people/{key}/samples", status_code=201)
def add_sample(key: str, body: Sample):
    with errors():
        return library.add_sample(key, body.source, body.start, body.end, body.cleaned, body.consent)


@router.get("/audio/{key}")
def sample_audio(key: str):
    with errors():
        library.read("samples", key)
        return FileResponse(library.location("samples", key) / "audio.wav", media_type="audio/wav")


class Version(BaseModel):
    samples: list[str] = Field(min_length=1, max_length=40)


@router.post("/people/{key}/versions", status_code=201)
def build(key: str, body: Version):
    with errors():
        return library.build_version(key, body.samples)


class Active(BaseModel):
    voice: str = Field(pattern=r"^clone:[0-9a-f]{12}$")


@router.post("/people/{key}/active")
def activate(key: str, body: Active):
    with errors():
        return library.activate(key, body.voice)
