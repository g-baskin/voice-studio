#!/usr/bin/env bash
# Isolated CPU media engine. Run explicitly; never invoked by a web request.
set -euo pipefail
cd "$(dirname "$0")/.."
uv sync --project engines/media --locked
engines/media/.venv/bin/python scripts/download_media_models.py
