#!/usr/bin/env bash
# Download the base models Shark Audio needs (about 385 MB) into models/. Safe to re-run: verified files are skipped.
# Usage: scripts/download_models.sh [target-dir]      (default: models/)
# Optional extras: scripts/setup_clone_engine.sh installs the voice-cloning engine (about 3.3 GB).
set -euo pipefail
cd "$(dirname "$0")/.."
DEST="${1:-models}"
mkdir -p "$DEST"

get() { # file url sha256
  local file="$1" url="$2" sum="$3" dst="$DEST/$1"
  if [ -f "$dst" ] && [ "$(shasum -a 256 "$dst" | cut -d' ' -f1)" = "$sum" ]; then
    echo "    ok  $file"
    return
  fi
  rm -f "$dst"
  echo "    get $file"
  curl -fL --retry 3 -C - --progress-bar -o "$dst.part" "$url"
  if [ "$(shasum -a 256 "$dst.part" | cut -d' ' -f1)" != "$sum" ]; then
    rm -f "$dst.part"
    echo "Checksum mismatch for $file; not installed." >&2
    exit 1
  fi
  mv "$dst.part" "$dst"
}

echo "==> Voices (Kokoro, Apache-2.0)"
KOKORO=https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0
get kokoro-v1.0.onnx "$KOKORO/kokoro-v1.0.onnx" 7d5df8ecf7d4b1878015a32686053fd0eebe2bc377234608764cc0ef3636a6c5
get voices-v1.0.bin "$KOKORO/voices-v1.0.bin" bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d

echo "==> AI cleanup (GTCRN, MIT)"
get gtcrn_simple.onnx https://github.com/Xiaobin-Rong/gtcrn/raw/main/stream/onnx_models/gtcrn_simple.onnx \
  b4718df6228e7bdf1a8a435cf98f838636eb2fd331acabf86ba87c5192ebcb87

echo "==> Listener-rating scores (Microsoft DNSMOS, CC BY 4.0)"
DNS=https://github.com/microsoft/DNS-Challenge/raw/master/DNSMOS/DNSMOS
get dnsmos_sig_bak_ovr.onnx "$DNS/sig_bak_ovr.onnx" 269fbebdb513aa23cddfbb593542ecc540284a91849ac50516870e1ac78f6edd
get dnsmos_p808.onnx "$DNS/model_v8.onnx" 9246480c58567bc6affd4200938e77eef49468c8bc7ed3776d109c07456f6e91

echo "==> Voice matching (CAM++ speaker model, Apache-2.0)"
get 3dspeaker_campplus_en_voxceleb_16k.onnx \
  https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_campplus_sv_en_voxceleb_16k.onnx \
  357a834f702b80161e5b981182c038e18553c1f2ca752ed6cec2052365d4129b

echo "Done. Models are in $DEST/"
