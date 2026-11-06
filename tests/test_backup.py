import hashlib
import io
import json
import stat
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from naturalvoice import backup, server, voices


@pytest.fixture
def data(tmp_path, monkeypatch):
    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setattr(voices, "DATA_DIR", root)
    for name, value in {
        "projects/demo.json": b'{"title":"Original"}',
        "voices/custom.npy": b"vector",
        "voices/clone.wav": b"reference",
        "sample-library/sources/abc/input.wav": b"original source",
        "sample-library/people/abc/record.json": b'{"versions":["clone"]}',
        "styles.json": b"[]",
        "favorites.json": b"[]",
        "llm.json": b"private key",
        "access-token": b"private token",
        "cache/features.npz": b"cache",
    }.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value)
    return root


def client():
    return TestClient(server.app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000))


def test_restore_drill(data, tmp_path):
    archive = tmp_path / "backup.zip"
    settings = {"nv-studio-draft-v1": '{"project":{"title":"Draft"}}'}
    backup.export_data(data, archive, settings)
    (data / "projects/canary.json").write_text("after backup")
    start = time.monotonic()
    restored, browser, count = backup.restore_data(archive, tmp_path)
    assert time.monotonic() - start < 10
    assert restored != data and count == 8 and browser == settings
    assert not (restored / "projects/canary.json").exists()
    assert (data / "projects/canary.json").exists()
    for name in backup.inventory(data):
        if "canary" not in name:
            assert (restored / name).read_bytes() == (data / name).read_bytes()
    for name in ["llm.json", "access-token", "cache"]:
        assert not (restored / name).exists()
    assert stat.S_IMODE(restored.stat().st_mode) == 0o700
    assert stat.S_IMODE(archive.stat().st_mode) == 0o600
    again, _, _ = backup.restore_data(archive, tmp_path)
    assert again != restored


def test_export_refuses_overwrite_and_symlink(data, tmp_path):
    archive = tmp_path / "backup.zip"
    archive.write_bytes(b"existing backup")
    with pytest.raises(FileExistsError):
        backup.export_data(data, archive, {})
    assert archive.read_bytes() == b"existing backup"
    (data / "voices/link.wav").symlink_to(data / "llm.json")
    with pytest.raises(ValueError, match="symbolic"):
        backup.export_data(data, tmp_path / "other.zip", {})


def archive_with(entries):
    output = io.BytesIO()
    manifest = {
        "format": "voice-studio-backup",
        "version": 1,
        "files": {
            name: {"size": len(value), "sha256": hashlib.sha256(value).hexdigest()} for name, value in entries.items()
        },
    }
    with zipfile.ZipFile(output, "w") as z:
        for name, value in entries.items():
            z.writestr(name, value)
        z.writestr("manifest.json", json.dumps(manifest))
    return output.getvalue()


@pytest.mark.parametrize(
    "name", ["../outside", "/absolute", "voices/../../bad", "voices\\bad", "llm.json", "access-token"]
)
def test_restore_rejects_unsafe_paths(name, tmp_path):
    path = tmp_path / "invalid.zip"
    path.write_bytes(archive_with({"browser-settings.json": b"{}", name: b"bad"}))
    with pytest.raises(ValueError):
        backup.restore_data(path, tmp_path)
    assert list(tmp_path.iterdir()) == [path]


def test_corruption_never_publishes_a_restore(data, tmp_path):
    path = tmp_path / "invalid.zip"
    payload = archive_with({"browser-settings.json": b"{}", "voices/ref.wav": b"original"})
    with zipfile.ZipFile(io.BytesIO(payload)) as old, zipfile.ZipFile(path, "w") as new:
        for item in old.infolist():
            new.writestr(item.filename, b"changed!" if item.filename == "voices/ref.wav" else old.read(item))
    with pytest.raises(ValueError, match="checksum"):
        backup.restore_data(path, tmp_path)
    assert not list(tmp_path.glob("voice-studio-restored-*"))
    assert (data / "voices/clone.wav").read_bytes() == b"reference"


def test_backup_api_roundtrip_and_guards(data):
    c = client()
    r = c.post("/api/backups/export", json={})
    assert r.status_code == 200 and r.content.startswith(b"PK")
    restored = c.post("/api/backups/restore", content=r.content)
    assert restored.status_code == 201
    assert Path(restored.json()["folder"]).is_dir()
    assert c.post("/api/backups/restore", content=b"bad").status_code == 400
    assert c.post("/api/backups/export", json={}, headers={"Origin": "https://other.example"}).status_code == 403
    remote = TestClient(server.app, base_url="http://127.0.0.1", client=("192.0.2.1", 50000))
    assert remote.post("/api/backups/export", json={}).status_code == 403
    assert server.processing.acquire(blocking=False)
    try:
        assert c.post("/api/backups/export", json={}).status_code == 409
    finally:
        server.processing.release()


def test_limits_and_browser_allowlist(data, tmp_path, monkeypatch):
    with pytest.raises(ValueError):
        backup.browser_settings({"access-token": '"secret"'})
    with pytest.raises(ValueError):
        backup.browser_settings({"nv-studio-draft-v1": "[]"})
    monkeypatch.setattr(backup, "MAX_BYTES", 1)
    with pytest.raises(ValueError, match="limit"):
        backup.export_data(data, tmp_path / "backup.zip", {})


def test_export_releases_processing_on_disk_failure(data, monkeypatch):
    from naturalvoice import backup_api

    def fail(**kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(backup_api.tempfile, "mkdtemp", fail)
    assert client().post("/api/backups/export", json={}).status_code == 400
    assert server.processing.acquire(blocking=False)
    server.processing.release()


def test_restore_duplicate_and_symlink_entries(tmp_path):
    path = tmp_path / "bad.zip"
    for variant in ("duplicate", "symlink"):
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("manifest.json", b"{}")
            if variant == "duplicate":
                z.writestr("voices/ref.wav", b"a")
                z.writestr("voices/REF.wav", b"b")
            else:
                info = zipfile.ZipInfo("voices/ref.wav")
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                z.writestr(info, "../../private")
        with pytest.raises(ValueError):
            backup.restore_data(path, tmp_path)
        assert not list(tmp_path.glob("voice-studio-restored-*"))


def test_manifest_limit_applies_to_export(data, tmp_path, monkeypatch):
    monkeypatch.setattr(backup, "MAX_JSON", 32)
    with pytest.raises(ValueError, match="manifest"):
        backup.export_data(data, tmp_path / "too-many.zip", {})


def test_gate_blocks_overlapping_writes_and_recovers():
    import asyncio
    from naturalvoice.backup_api import BackupGate

    async def exercise():
        entered = asyncio.Event()
        release = asyncio.Event()
        responses = []

        async def app(scope, receive, send):
            entered.set()
            await release.wait()

        async def send(message):
            responses.append(message)

        async def receive():
            return {"type": "http.request", "body": b""}

        gate = BackupGate(app)
        for first, second in (
            ("/api/studio/projects", "/api/backups/export"),
            ("/api/backups/export", "/api/studio/projects"),
        ):
            entered.clear()
            release.clear()
            task = asyncio.create_task(gate({"type": "http", "path": first, "method": "POST"}, receive, send))
            await entered.wait()
            await gate({"type": "http", "path": second, "method": "POST"}, receive, send)
            assert responses[-2]["status"] == 409
            release.set()
            await task
            assert gate.writers == 0 and gate.backing_up is False

    asyncio.run(exercise())


def test_restored_browser_settings_and_byte_limits(data, monkeypatch):
    settings = {"nv-studio-draft-v1": '{"project":{"title":"Draft"}}'}
    (data / "browser-settings.json").write_text(json.dumps(settings))
    assert client().get("/api/backups/browser").json() == settings
    monkeypatch.setattr(backup, "MAX_JSON", 8)
    assert client().post("/api/backups/export", content=b"x" * 9).status_code == 413
    assert client().get("/api/backups/browser").status_code == 400


def test_restore_folders_are_git_ignored():
    import subprocess
    from pathlib import Path

    subprocess.run(
        ["git", "check-ignore", "--no-index", "--quiet", "voice-studio-restored-fixture/voices/ref.wav"],
        cwd=Path(__file__).parents[1],
        check=True,
    )
