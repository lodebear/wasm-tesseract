#!/usr/bin/env bash
set -euo pipefail
DEST="${1:?usage: fetch-models.sh destination}"
digest_file() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1"; else shasum -a 256 "$1"; fi
}
fetch() {
  local quality="$1" revision="$2" lang="$3" digest="$4"
  mkdir -p "$DEST/$quality"
  local file="$DEST/$quality/$lang.traineddata"
  curl -fLsS --retry 3 "https://raw.githubusercontent.com/tesseract-ocr/tessdata_$quality/$revision/$lang.traineddata" -o "$file.part"
  [ "$(digest_file "$file.part" | cut -d' ' -f1)" = "$digest" ] || { echo "checksum mismatch: $file" >&2; exit 1; }
  mv "$file.part" "$file"
}
fetch fast 87416418657359cb625c412a48b6e1d6d41c29bd eng 7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2
fetch fast 87416418657359cb625c412a48b6e1d6d41c29bd deu 19d219bbb6672c869d20a9636c6816a81eb9a71796cb93ebe0cb1530e2cdb22d
fetch best e12c65a915945e4c28e237a9b52bc4a8f39a0cec eng 8280aed0782fe27257a68ea10fe7ef324ca0f8d85bd2fd145d1c2b560bcb66ba
fetch best e12c65a915945e4c28e237a9b52bc4a8f39a0cec deu 8407331d6aa0229dc927685c01a7938fc5a641d1a9524f74838cdac599f0d06e
