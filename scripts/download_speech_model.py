"""Fetch the pinned Parakeet TDT 0.6B v2 int8 speech model with exact sizes and SHA-256 checks."""

from __future__ import annotations

import hashlib
import shutil
import urllib.request
from pathlib import Path

REPO = "csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
REVISION = "1ab9323565ddb038682214b292f588070a538ce2"
BASE = f"https://huggingface.co/{REPO}/resolve/{REVISION}"
ROOT = Path(__file__).resolve().parents[1] / "engines/media/models/asr"
FREE_BYTES = 1400 * 1024**2
ASSETS = (
    ("encoder.int8.onnx", 652_184_296, "a32b12d17bbbc309d0686fbbcc2987b5e9b8333a7da83fa6b089f0a2acd651ab"),
    ("decoder.int8.onnx", 7_257_753, "b6bb64963457237b900e496ee9994b59294526439fbcc1fecf705b31a15c6b4e"),
    ("joiner.int8.onnx", 1_739_080, "7946164367946e7f9f29a122407c3252b680dbae9a51343eb2488d057c3c43d2"),
    ("tokens.txt", 9_384, "ec182b70dd42113aff6c5372c75cac58c952443eb22322f57bbd7f53977d497d"),
)
ATTRIBUTION = f"""Speech recognition model: NVIDIA Parakeet TDT 0.6B v2 (English), int8 ONNX export by sherpa-onnx.
Original model: https://huggingface.co/nvidia/parakeet-tdt-0.6b-v2 (c) NVIDIA, licensed CC-BY-4.0.
License: https://creativecommons.org/licenses/by/4.0/
Converted files: https://huggingface.co/{REPO} (revision {REVISION}).
Changes: quantised to int8 and exported to ONNX by the sherpa-onnx project; used unmodified here.
"""


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fetch(name: str, size: int, expected: str) -> None:
    dst = ROOT / name
    if dst.is_file() and dst.stat().st_size == size and digest(dst) == expected:
        return
    part = dst.with_name(dst.name + ".part")
    try:
        with urllib.request.urlopen(f"{BASE}/{name}", timeout=60) as response, part.open("wb") as output:
            received = 0
            while chunk := response.read(1024**2):
                received += len(chunk)
                if received > size:
                    raise ValueError(f"Download exceeds its expected size: {name}")
                output.write(chunk)
        if received != size or digest(part) != expected:
            raise ValueError(f"Checksum mismatch: {name}")
        part.replace(dst)
    finally:
        part.unlink(missing_ok=True)


def main() -> None:
    if not BASE.startswith("https://"):
        raise SystemExit("Model downloads must use HTTPS.")
    ROOT.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(ROOT).free < FREE_BYTES:
        raise SystemExit("Keep 1.4 GB free before installing the speech model.")
    for name, size, expected in ASSETS:
        print(f"Fetching {name} ({size / 1024**2:.1f} MB)", flush=True)
        fetch(name, size, expected)
    (ROOT / "ATTRIBUTION.txt").write_text(ATTRIBUTION, encoding="utf-8")
    print("Speech model installed and SHA-256 checks passed.")


if __name__ == "__main__":
    main()
