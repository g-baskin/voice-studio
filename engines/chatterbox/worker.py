"""Persistent Chatterbox-Turbo (ONNX) worker. JSON lines over stdin/stdout; models loaded once.

Requests:  {"id": 1, "op": "ping"}
           {"id": 2, "op": "speak", "text": "...", "ref": "/abs/ref.wav", "out": "/abs/out.npy", "seed": 0}
           {"id": 3, "op": "convert", "src": "/abs/source.wav", "ref": "/abs/ref.wav", "out": "/abs/out.npy"}
Responses: {"id": .., "ok": true, ...} or {"id": .., "ok": false, "error": "..."}
The reference must be a 24 kHz mono 16-bit WAV (the app preprocesses it). Audio is written as float32 .npy.
Logs go to stderr so stdout stays a clean protocol channel.
"""

from __future__ import annotations

import json
import os
import sys
import time
import wave
from pathlib import Path

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

HERE = Path(__file__).resolve().parent
MODELS = Path(os.environ.get("CHATTERBOX_MODELS", HERE / "models"))
SR = 24000
START, STOP, SILENCE = 6561, 6562, 4299
NUM_KV_HEADS, HEAD_DIM = 16, 64
REP_PENALTY = 1.2


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def _sess(name: str, dtype: str) -> ort.InferenceSession:
    suffix = "" if dtype == "fp32" else "_quantized"
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = int(os.environ.get("NATURALVOICE_CLONE_THREADS", 2))
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    return ort.InferenceSession(str(MODELS / "onnx" / f"{name}{suffix}.onnx"), opts, providers=["CPUExecutionProvider"])


class Engine:
    def __init__(self):
        dt_file = MODELS / "DTYPE"
        self.dtype = dt_file.read_text().strip() if dt_file.exists() else "fp32"
        t = time.time()
        self.tok = Tokenizer.from_file(str(MODELS / "tokenizer.json"))
        self.enc = _sess("speech_encoder", self.dtype)
        self.emb = _sess("embed_tokens", self.dtype)
        self.lm = _sess("language_model", self.dtype)
        self.dec = _sess("conditional_decoder", self.dtype)
        self.kv_inputs = [
            (i.name, np.float16 if i.type == "tensor(float16)" else np.float32)
            for i in self.lm.get_inputs()
            if "past_key_values" in i.name
        ]
        self._cond: dict[tuple[str, float], tuple] = {}
        log(f"chatterbox loaded ({self.dtype}) in {time.time() - t:.1f}s")

    def cond(self, ref: str):
        key = (ref, os.path.getmtime(ref))
        if key not in self._cond:
            with wave.open(ref, "rb") as w:
                if w.getframerate() != SR or w.getnchannels() != 1 or w.getsampwidth() != 2:
                    raise ValueError("Reference must be 24 kHz mono 16-bit WAV.")
                pcm = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768
            self._cond.clear()  # keep one voice cached; references are small to re-encode
            self._cond[key] = tuple(self.enc.run(None, {"audio_values": pcm[None, :]}))
        return self._cond[key]

    def convert(self, src: str, ref: str) -> np.ndarray:
        """Voice conversion (upstream ChatterboxVC recipe): S3 tokens of the source, decoded with the
        target voice's prompt tokens + speaker embedding/features."""
        _, prompt_token, spk_emb, spk_feat = self.cond(ref)
        with wave.open(src, "rb") as w:
            if w.getframerate() != SR or w.getnchannels() != 1 or w.getsampwidth() != 2:
                raise ValueError("Source must be 24 kHz mono 16-bit WAV.")
            pcm = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768
        tokens = self.enc.run(None, {"audio_values": pcm[None, :]})[1].astype(np.int64)
        tokens = np.concatenate([prompt_token, tokens, np.full((1, 3), SILENCE, dtype=np.int64)], axis=1)
        wav = self.dec.run(None, dict(speech_tokens=tokens, speaker_embeddings=spk_emb, speaker_features=spk_feat))[
            0
        ].squeeze(0)
        return np.asarray(wav, dtype=np.float32).reshape(-1)

    def speak(self, text: str, ref: str, seed: int = 0) -> np.ndarray:
        cond_emb, prompt_token, spk_emb, spk_feat = self.cond(ref)
        ids = np.array([self.tok.encode(text).ids], dtype=np.int64)
        embeds = np.concatenate((cond_emb, self.emb.run(None, {"input_ids": ids})[0]), axis=1)
        b, n, _ = embeds.shape
        past = {k: np.zeros([b, NUM_KV_HEADS, 0, HEAD_DIM], dtype=t) for k, t in self.kv_inputs}
        mask = np.ones((b, n), dtype=np.int64)
        pos = np.arange(n, dtype=np.int64)[None, :]
        gen = [START]
        # ~25 speech tokens per second; allow generous room for slow speech, stop runaway loops
        max_new = min(1000, 60 + 8 * len(text))
        for _ in range(max_new):
            logits, *present = self.lm.run(
                None, dict(inputs_embeds=embeds, attention_mask=mask, position_ids=pos, **past)
            )
            scores = logits[:, -1, :].astype(np.float32)
            seen = np.unique(np.array(gen))
            s = scores[0, seen]
            scores[0, seen] = np.where(s < 0, s * REP_PENALTY, s / REP_PENALTY)
            nxt = int(np.argmax(scores[0]))
            gen.append(nxt)
            if nxt == STOP:
                break
            embeds = self.emb.run(None, {"input_ids": np.array([[nxt]], dtype=np.int64)})[0]
            mask = np.concatenate([mask, np.ones((b, 1), dtype=np.int64)], axis=1)
            pos = pos[:, -1:] + 1
            for j, (k, _) in enumerate(self.kv_inputs):
                past[k] = present[j]
        speech = np.array([[t for t in gen[1:] if t < START]], dtype=np.int64)
        if speech.shape[1] == 0:
            raise RuntimeError("The model produced no speech for this text.")
        tokens = np.concatenate([prompt_token, speech, np.full((1, 3), SILENCE, dtype=np.int64)], axis=1)
        wav = self.dec.run(None, dict(speech_tokens=tokens, speaker_embeddings=spk_emb, speaker_features=spk_feat))[
            0
        ].squeeze(0)
        return np.asarray(wav, dtype=np.float32).reshape(-1)


def main():
    out = sys.stdout
    sys.stdout = sys.stderr  # stray prints from libraries can't corrupt the protocol
    try:
        eng = Engine()
    except Exception as e:  # report and exit; the client shows a clear error
        out.write(json.dumps({"id": 0, "ok": False, "error": f"Engine failed to load: {e}"}) + "\n")
        out.flush()
        return
    out.write(json.dumps({"id": 0, "ok": True, "ready": True, "dtype": eng.dtype}) + "\n")
    out.flush()
    for line in sys.stdin:
        try:
            req = json.loads(line)
        except ValueError:
            continue
        rid = req.get("id")
        try:
            if req.get("op") == "ping":
                resp = {"id": rid, "ok": True}
            elif req.get("op") == "speak":
                t = time.time()
                wav = eng.speak(str(req["text"]), str(req["ref"]), int(req.get("seed", 0)))
                np.save(req["out"], wav)
                resp = {"id": rid, "ok": True, "sr": SR, "samples": int(wav.size), "secs": time.time() - t}
            elif req.get("op") == "convert":
                t = time.time()
                wav = eng.convert(str(req["src"]), str(req["ref"]))
                np.save(req["out"], wav)
                resp = {"id": rid, "ok": True, "sr": SR, "samples": int(wav.size), "secs": time.time() - t}
            else:
                resp = {"id": rid, "ok": False, "error": "Unknown op."}
        except Exception as e:
            log("worker error:", repr(e))
            resp = {"id": rid, "ok": False, "error": str(e)}
        out.write(json.dumps(resp) + "\n")
        out.flush()


if __name__ == "__main__":
    main()
