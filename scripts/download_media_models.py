"""Fetch pinned media models and extract only named regular files, never archive paths."""

from __future__ import annotations

import hashlib
import shutil
import tarfile
import urllib.request
from pathlib import Path

BASE = "https://github.com/k2-fsa/sherpa-onnx/releases/download"
ROOT = Path(__file__).resolve().parents[1] / "engines/media/models"
ASSETS = (
    (
        "segmentation.tar.bz2",
        "speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2",
        "24615ee884c897d9d2ba09bb4d30da6bb1b15e685065962db5b02e76e4996488",
    ),
    (
        "embedding.onnx",
        "speaker-recongition-models/3dspeaker_speech_eres2net_sv_en_voxceleb_16k.onnx",
        "c59158379255ad66e161679cca6af8d52d51e389e3224ab7d7a7baae295c2db5",
    ),
    (
        "separation.tar.bz2",
        "source-separation-models/sherpa-onnx-spleeter-2stems.tar.bz2",
        "e26401d9c1801f43c0229731d78d32c2e80085e3aceedeb25f29d2de5fa68ca2",
    ),
)
MEMBERS = (
    ("segmentation.tar.bz2", "sherpa-onnx-pyannote-segmentation-3-0/model.onnx", "segmentation.onnx"),
    ("segmentation.tar.bz2", "sherpa-onnx-pyannote-segmentation-3-0/LICENSE", "segmentation-LICENSE"),
    ("separation.tar.bz2", "sherpa-onnx-spleeter-2stems/vocals.onnx", "vocals.onnx"),
    ("separation.tar.bz2", "sherpa-onnx-spleeter-2stems/accompaniment.onnx", "accompaniment.onnx"),
)


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(ROOT).free < 1024**3:
        raise SystemExit("Keep 1 GB free before installing models.")
    for name, remote, expected in ASSETS:
        dst = ROOT / name
        if dst.is_file() and digest(dst) == expected:
            continue
        part = dst.with_suffix(dst.suffix + ".part")
        try:
            with urllib.request.urlopen(f"{BASE}/{remote}", timeout=60) as response, part.open("wb") as output:
                size = 0
                while chunk := response.read(1024**2):
                    size += len(chunk)
                    if size > 100 * 1024**2:
                        raise ValueError("Model download exceeds its size limit.")
                    output.write(chunk)
            if digest(part) != expected:
                raise ValueError(f"Checksum mismatch: {name}")
            part.replace(dst)
        finally:
            part.unlink(missing_ok=True)
    for archive, member, name in MEMBERS:
        with tarfile.open(ROOT / archive, "r:bz2") as bundle:
            info = bundle.getmember(member)
            if not info.isfile() or info.size > 150 * 1024**2:
                raise ValueError("Unexpected archive member.")
            stream = bundle.extractfile(info)
            if stream is None:
                raise ValueError("Missing model data.")
            part = ROOT / f"{name}.part"
            try:
                with stream, part.open("wb") as output:
                    shutil.copyfileobj(stream, output)
                part.replace(ROOT / name)
            finally:
                part.unlink(missing_ok=True)
    print("Media models installed and archive SHA-256 checks passed.")


if __name__ == "__main__":
    main()
