from __future__ import annotations

import json
import shutil
import shlex
import zlib
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.background import BackgroundTask
from starlette.types import ASGIApp, Receive, Scope, Send

from . import backup, voices
from .sample_library_api import local_request

router = APIRouter(prefix="/api/backups", dependencies=[Depends(local_request)])


class BackupGate:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.writers = 0
        self.backing_up = False

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith("/api/"):
            await self.app(scope, receive, send)
            return
        exclusive = scope["path"].startswith("/api/backups/") and scope["method"] == "POST"
        writing = scope["method"] not in {"GET", "HEAD", "OPTIONS"}
        if writing and (self.backing_up or (exclusive and self.writers)):
            await JSONResponse({"detail": "Another write is active. Wait, then retry."}, status_code=409)(
                scope, receive, send
            )
            return
        if exclusive:
            self.backing_up = True
        elif writing:
            self.writers += 1
        try:
            await self.app(scope, receive, send)
        finally:
            if exclusive:
                self.backing_up = False
            elif writing:
                self.writers -= 1


@router.post("/export")
async def export_backup(request: Request) -> FileResponse:
    from .server import processing

    payload = bytearray()
    async for chunk in request.stream():
        payload.extend(chunk)
        if len(payload) > backup.MAX_JSON:
            raise HTTPException(413, "Browser settings exceed 2 MB.")
    try:
        settings = backup.browser_settings(json.loads(payload))
    except (ValueError, UnicodeError):
        raise HTTPException(400, "Invalid browser settings.") from None
    if not processing.acquire(blocking=False):
        raise HTTPException(409, "An audio job is running. Wait until it finishes before backing up.")
    folder = None
    try:
        folder = Path(tempfile.mkdtemp(prefix="voice-studio-backup-"))
        from starlette.concurrency import run_in_threadpool

        archive = folder / "voice-studio-backup.zip"
        await run_in_threadpool(backup.export_data, voices.DATA_DIR, archive, settings)
        return FileResponse(
            archive,
            filename="voice-studio-backup.zip",
            media_type="application/zip",
            headers={"Cache-Control": "no-store"},
            background=BackgroundTask(shutil.rmtree, folder),
        )
    except BaseException as error:
        if folder is not None:
            shutil.rmtree(folder)
        if isinstance(error, (ValueError, OSError)):
            raise HTTPException(400, "Backup failed. Check free space and finish other writes, then retry.") from None
        raise
    finally:
        processing.release()


@router.post("/restore", status_code=201)
async def restore_backup(request: Request) -> dict:
    from starlette.concurrency import run_in_threadpool

    with tempfile.TemporaryDirectory(prefix="voice-studio-upload-") as temporary:
        path = Path(temporary) / "backup.zip"
        size = 0
        with path.open("xb") as output:
            async for chunk in request.stream():
                size += len(chunk)
                if size > backup.MAX_BYTES + 32 * 1024**2:
                    raise HTTPException(413, "Backup exceeds 4 GB.")
                output.write(chunk)
        try:
            folder, settings, count = await run_in_threadpool(
                backup.restore_data, path, voices.DATA_DIR.resolve().parent
            )
        except (ValueError, OSError, zipfile.BadZipFile, RuntimeError, zlib.error, EOFError):
            raise HTTPException(
                400, "Restore failed: invalid backup or insufficient disk space. Current data is unchanged."
            ) from None
    return {
        "folder": str(folder),
        "files": count,
        "browser": settings,
        "restart": f"NATURALVOICE_DATA={shlex.quote(str(folder))} uv run voicestudio serve --open",
    }


@router.get("/browser")
def restored_browser_settings() -> dict[str, str]:
    path = voices.DATA_DIR / "browser-settings.json"
    if not path.exists():
        return {}
    try:
        if path.stat().st_size > backup.MAX_JSON:
            raise ValueError
        return backup.browser_settings(json.loads(path.read_text()))
    except (OSError, ValueError):
        raise HTTPException(400, "Saved browser settings are invalid.") from None
