#!/bin/bash
# Double-click on a Mac to open Shark Audio as a desktop app (local server + browser window).
cd "$(dirname "$0")/.." || exit 1
exec uv run sharkaudio serve --open
