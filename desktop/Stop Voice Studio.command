#!/bin/bash
# Stops the Voice Studio engine started by the app (port 8765 by default).
PORT="${NATURALVOICE_PORT:-8765}"
PIDS=$(lsof -nP -tiTCP:"$PORT" -sTCP:LISTEN)
if [ -z "$PIDS" ]; then echo "Voice Studio is not running."; exit 0; fi
kill $PIDS && echo "Voice Studio stopped."
