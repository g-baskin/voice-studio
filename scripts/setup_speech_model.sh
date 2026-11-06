#!/usr/bin/env bash
# Local speech-to-text for the Editor (about 661 MB). Run explicitly; never invoked by a web request.
set -euo pipefail
cd "$(dirname "$0")/.."
uv sync --project engines/media --locked
engines/media/.venv/bin/python scripts/download_speech_model.py
