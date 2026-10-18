#!/usr/bin/env bash
# Install the zero-shot voice cloning engine (Chatterbox-Turbo, ONNX, MIT licence) project-locally.
# Everything goes under engines/chatterbox/ (own venv + models/). Safe to re-run: verified files are skipped.
# Usage: scripts/setup_clone_engine.sh [fp32|q8|all]   (default fp32 ~3.3 GB; q8 adds/uses ~1.1 GB; all = both)
set -euo pipefail
cd "$(dirname "$0")/.."
ENGINE=engines/chatterbox
DTYPE="${1:-fp32}"
REV=d21799bd0354adb85e348b8a0442a8405110a2cf # pinned commit of ResembleAI/chatterbox-turbo-ONNX
BASE="https://huggingface.co/ResembleAI/chatterbox-turbo-ONNX/resolve/$REV"
MODELS="$ENGINE/models"

command -v uv >/dev/null || {
  echo "uv is required (https://docs.astral.sh/uv/)"
  exit 1
}
echo "==> Python environment in $ENGINE/.venv"
(cd "$ENGINE" && uv sync --quiet)

mkdir -p "$MODELS/onnx"
fetch() { # path sha256(or -)
  local path="$1" sum="$2" dst="$MODELS/$1"
  if [ -f "$dst" ]; then
    if [ "$sum" = "-" ] || [ "$(shasum -a 256 "$dst" | cut -d' ' -f1)" = "$sum" ]; then
      echo "    ok  $path"
      return
    fi
    echo "    bad checksum, re-downloading $path"
    rm -f "$dst"
  fi
  echo "    get $path"
  curl -fL --retry 3 -C - -o "$dst.part" "$BASE/$path"
  if [ "$sum" != "-" ] && [ "$(shasum -a 256 "$dst.part" | cut -d' ' -f1)" != "$sum" ]; then
    rm -f "$dst.part"
    echo "Checksum mismatch for $path"
    exit 1
  fi
  mv "$dst.part" "$dst"
}

echo "==> Model files ($DTYPE) in $MODELS"
fetch tokenizer.json -
fetch tokenizer_config.json -
fetch config.json -
if [ "$DTYPE" = "q8" ] || [ "$DTYPE" = "all" ]; then
  fetch onnx/conditional_decoder_quantized.onnx 2af3b150196d9d559cd3c91e03da80eb27a466032369dc2b57ea729cddad3ebb
  fetch onnx/conditional_decoder_quantized.onnx_data 4918ca09e05e41d2b4aa1ace6201d1cd911ffc58a42801002bab177d495cfe0a
  fetch onnx/embed_tokens_quantized.onnx 0efe1bc01c2c48a98425a74444fd9887924d887f922c2722a6ec961ebb9e1db6
  fetch onnx/embed_tokens_quantized.onnx_data 9025d04c124899823124b1d7bb7069b1f535fb8a6c2d88f97520eb6fecced986
  fetch onnx/language_model_quantized.onnx 0b40581277e30b7034331ec8c3ad47ed71d321f015b387a95221e54e2fcbfde8
  fetch onnx/language_model_quantized.onnx_data ec9945df36cb5d131d46688f2609fd715fbfcb0b8ee9681af5c84118de2d55a2
  fetch onnx/speech_encoder_quantized.onnx 5b6f15870a43cf97892df86fc550a0ef4763522d527cde72b2a4316f80a34de4
  fetch onnx/speech_encoder_quantized.onnx_data d59861fb55e806fbeee731da9d4f8ff819fb5735de5d15e262d902594ee4dbb6
fi
if [ "$DTYPE" != "q8" ]; then
  fetch onnx/conditional_decoder.onnx 8c43f3a1d0ddb1a86e226a244d7cda5396c67f5c6412789c23900c646e3ffc50
  fetch onnx/conditional_decoder.onnx_data 05f162a519f3e9abaf0b7337ae037f4af8b2b30c4455d39b2c61ed3a9b2b5476
  fetch onnx/embed_tokens.onnx 27796e8252f36b463b0421cafdcc35b5f1e670ab0d96c9182f37ac6571c2f4bc
  fetch onnx/embed_tokens.onnx_data a1c37edc6ec6adb655351f02e958da297221b50211c2c01b69312cb6f008a293
  fetch onnx/language_model.onnx c12e31df78c74f9589b165c8d51e65171f5028b77b7fedb41900f55f7f410dc8
  fetch onnx/language_model.onnx_data 67db106868f5354b2e425651f1791aef36ae3e6f00ac5e1d91e32c985cad6b39
  fetch onnx/speech_encoder.onnx 4d66128037517dd51d370edc9b89ce36d42c75dcbd96e7216c7fb45dfae36045
  fetch onnx/speech_encoder.onnx_data c9915ff6c529e7bb80983b525255e6744d6c39c7e35b12720925ba99ed0d0a2f
fi
# DTYPE = default precision when NATURALVOICE_CLONE_PRECISION is unset
[ "$DTYPE" = "all" ] && echo fp32 >"$MODELS/DTYPE" || echo "$DTYPE" >"$MODELS/DTYPE"

echo "==> Speaker-similarity model (WeSpeaker ResNet34-LM, Apache-2.0) in engines/eval/models"
EVAL=engines/eval/models
mkdir -p "$EVAL"
SPK=voxceleb_resnet34_LM.onnx
SPK_SUM=7bb2f06e9df17cdf1ef14ee8a15ab08ed28e8d0ef5054ee135741560df2ec068
if [ ! -f "$EVAL/$SPK" ] || [ "$(shasum -a 256 "$EVAL/$SPK" | cut -d' ' -f1)" != "$SPK_SUM" ]; then
  curl -fL --retry 3 -o "$EVAL/$SPK.part" "https://huggingface.co/Wespeaker/wespeaker-voxceleb-resnet34-LM/resolve/main/$SPK"
  [ "$(shasum -a 256 "$EVAL/$SPK.part" | cut -d' ' -f1)" = "$SPK_SUM" ] || {
    rm -f "$EVAL/$SPK.part"
    echo "Checksum mismatch for $SPK"
    exit 1
  }
  mv "$EVAL/$SPK.part" "$EVAL/$SPK"
else echo "    ok  $SPK"; fi
echo "==> Done. Chatterbox-Turbo ($DTYPE) installed in $ENGINE"
