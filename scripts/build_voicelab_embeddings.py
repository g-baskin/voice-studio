"""Precompute speaker embeddings of the English stock voices for Voice Lab "Match".

Writes src/naturalvoice/voicelab_embeddings.npz (names, emb, pitch, bright, fingerprint). Match loads it only
while the fingerprint (Kokoro voices file + speaker model + measure line) still matches. ~6 min on an Intel i5.
Run: uv run python scripts/build_voicelab_embeddings.py
"""

import time

from naturalvoice import voicelab as vl, voices as vlib

t0 = time.time()
feats = {}
names = [n for n in vl._stock_names() if n[0] in "ab"]
for i, n in enumerate(names, 1):
    a = vl.render(vlib.style_of(n), "en-us", vl.MEASURE_LINE)
    feats[n] = {"emb": vl.embed(a, vl.SR), "pitch": vl.pitch_hz(a), "brightness": vl.brightness_hz(a)}
    print(f"{i}/{len(names)} {n} {time.time() - t0:.0f}s", flush=True)
vl.save_features(vl.SHIPPED_EMB, feats, vl.model_fingerprint())
print(f"wrote {len(feats)} voices in {time.time() - t0:.0f} s", flush=True)
