from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

MAX_BYTES = 4 * 1024**3
MAX_FILES = 20000
MAX_JSON = 2 * 1024**2
ROOTS = frozenset({"voices", "projects", "sample-library"})
FILES = frozenset({"styles.json", "favorites.json", "browser-settings.json"})
BROWSER_KEYS = frozenset({"nv-studio-draft-v1", "naturalvoice.templates.v1"})


def browser_settings(value: object) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) - BROWSER_KEYS:
        raise ValueError("Unsupported browser settings.")
    result: dict[str, str] = {}
    for key, text in value.items():
        if not isinstance(text, str) or len(text.encode()) > MAX_JSON:
            raise ValueError("Browser settings are too large or invalid.")
        if not isinstance(json.loads(text), dict):
            raise ValueError("Browser settings must contain JSON objects.")
        result[key] = text
    if len(json.dumps(result).encode()) > MAX_JSON:
        raise ValueError("Browser settings exceed 2 MB.")
    return result


def allowed(name: str) -> bool:
    parts = PurePosixPath(name).parts
    return bool(
        parts
        and str(PurePosixPath(name)) == name
        and not name.startswith("/")
        and all(re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9_. -]*", p) for p in parts)
        and all(p not in {".", ".."} for p in parts)
        and (name in FILES or (len(parts) > 1 and parts[0] in ROOTS))
    )


def inventory(root: Path) -> dict[str, tuple[int, int, int]]:
    found: dict[str, tuple[int, int, int]] = {}
    for name in sorted(ROOTS | (FILES - {"browser-settings.json"})):
        base = root / name
        if base.is_symlink():
            raise ValueError("Backup refuses symbolic links.")
        if not base.exists():
            continue
        paths = sorted(base.rglob("*")) if base.is_dir() else [base]
        for path in paths:
            if path.is_symlink():
                raise ValueError("Backup refuses symbolic links.")
            if path.is_dir() or path.name == ".write.lock":
                continue
            relative = path.relative_to(root).as_posix()
            if not allowed(relative) or not path.is_file():
                raise ValueError("Unsupported or unfinished data file. Finish other work before backing up.")
            info = path.stat()
            found[relative] = (info.st_size, info.st_mtime_ns, info.st_ino)
    if len(found) > MAX_FILES or sum(item[0] for item in found.values()) > MAX_BYTES:
        raise ValueError("Backup exceeds the 4 GB or 20,000 file limit.")
    return found


def export_data(root: Path, destination: Path, settings: dict[str, str]) -> None:
    settings = browser_settings(settings)
    before = inventory(root)
    entries: dict[str, dict[str, str | int]] = {}
    # Exclusive creation protects an earlier backup even if a caller reuses its filename.
    with destination.open("xb") as output:
        os.chmod(destination, 0o600)
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name in before:
                digest = hashlib.sha256()
                size = 0
                with (root / name).open("rb") as source, archive.open(name, "w", force_zip64=True) as target:
                    while chunk := source.read(1024**2):
                        size += len(chunk)
                        if size > before[name][0]:
                            raise ValueError("Data changed during backup. Retry when the app is idle.")
                        digest.update(chunk)
                        target.write(chunk)
                entries[name] = {"size": size, "sha256": digest.hexdigest()}
            payload = json.dumps(settings, sort_keys=True).encode()
            archive.writestr("browser-settings.json", payload)
            entries["browser-settings.json"] = {"size": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
            if inventory(root) != before:
                raise ValueError("Data changed during backup. Retry when the app is idle.")
            manifest = json.dumps({"format": "voice-studio-backup", "version": 1, "files": entries}).encode()
            if len(manifest) > MAX_JSON:
                raise ValueError("Backup manifest exceeds 2 MB. Reduce the number of files.")
            archive.writestr("manifest.json", manifest)
        output.flush()
        os.fsync(output.fileno())


def restore_data(archive_path: Path, parent: Path) -> tuple[Path, dict[str, str], int]:
    if archive_path.stat().st_size > MAX_BYTES + 32 * 1024**2:
        raise ValueError("Backup file exceeds 4 GB.")
    with zipfile.ZipFile(archive_path) as archive:
        infos = archive.infolist()
        names = [item.filename for item in infos]
        if len(infos) > MAX_FILES + 2 or len(set(n.casefold() for n in names)) != len(names):
            raise ValueError("Too many or duplicate archive entries.")
        if "manifest.json" not in names or archive.getinfo("manifest.json").file_size > MAX_JSON:
            raise ValueError("Missing or oversized backup manifest.")
        for item in infos:
            mode = item.external_attr >> 16
            if (
                (item.filename != "manifest.json" and not allowed(item.filename))
                or item.is_dir()
                or stat.S_IFMT(mode) not in {0, stat.S_IFREG}
                or item.flag_bits & 1
                or item.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
            ):
                raise ValueError("Unsupported archive entry.")
        if sum(item.file_size for item in infos) > MAX_BYTES + MAX_JSON * 2:
            raise ValueError("Expanded backup exceeds 4 GB.")
        manifest = json.loads(archive.read("manifest.json"))
        if (
            not isinstance(manifest, dict)
            or manifest.get("format") != "voice-studio-backup"
            or manifest.get("version") != 1
        ):
            raise ValueError("Unsupported backup format or version.")
        entries = manifest.get("files")
        if not isinstance(entries, dict) or set(entries) != set(names) - {"manifest.json"}:
            raise ValueError("Backup manifest does not match its files.")
        if "browser-settings.json" not in entries or archive.getinfo("browser-settings.json").file_size > MAX_JSON:
            raise ValueError("Missing or oversized browser settings.")
        for name, record in entries.items():
            if (
                not isinstance(record, dict)
                or record.get("size") != archive.getinfo(name).file_size
                or not isinstance(record.get("sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", record["sha256"])
            ):
                raise ValueError("Invalid backup checksum record.")
        folder = Path(tempfile.mkdtemp(prefix="voice-studio-restored-", dir=parent))
        try:
            for name, record in sorted(entries.items()):
                target = folder / name
                target.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256()
                with archive.open(name) as source, target.open("xb") as output:
                    os.chmod(target, 0o600)
                    while chunk := source.read(1024**2):
                        digest.update(chunk)
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                if digest.hexdigest() != record["sha256"]:
                    raise ValueError("Backup checksum mismatch. Nothing was restored.")
            settings = browser_settings(json.loads((folder / "browser-settings.json").read_text()))
            return folder, settings, len(entries)
        except BaseException:
            shutil.rmtree(folder)  # Only the exclusive directory created by this restore attempt.
            raise
