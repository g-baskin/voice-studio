"""Measure pitch and brightness of the English stock voices for keyword voice design.

Writes src/naturalvoice/voicelab_features.json. Run: uv run python scripts/build_voicelab_features.py
"""
import json
import sys
import time
from pathlib import Path

from naturalvoice import voicelab as vl, voices as vlib

LINE = "The morning light settled over the quiet harbour, and everyone stopped to listen."
OUT = Path(__file__).resolve().parents[1] / "src/naturalvoice/voicelab_features.json"
prefixes = sys.argv[1] if len(sys.argv) > 1 else "ab"
t0 = time.time()
feats = {}
for n in vl._stock_names():
    if n[0] in prefixes:
        a = vl.render(vlib.style_of(n), "en-us", LINE)
        feats[n] = {"pitch": round(vl.pitch_hz(a), 1), "brightness": round(vl.brightness_hz(a), 1)}
        print(n, feats[n], flush=True)
OUT.write_text(json.dumps({"line": LINE, "measured": "pitch = median F0 (Hz), brightness = spectral centroid (Hz)",
                           "voices": feats}, indent=1))
print(f"{len(feats)} voices in {time.time() - t0:.0f} s")
