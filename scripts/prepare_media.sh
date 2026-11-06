#!/usr/bin/env bash
# Compress a LICENSED source clip into web-friendly hero media (<6 MB each) and update the manifest.
#
#   scripts/prepare_media.sh path/to/your-licensed-clip.mp4
#
# Produces in frontend/public/media (override with OUT_DIR=...):
#   hero.mp4  (H.264, faststart)   hero.webm (VP9)   hero-poster.jpg   manifest.json
# Needs ffmpeg. Never commit footage you do not hold a licence for (see frontend/public/media/CREDITS.md).
set -euo pipefail

SRC="${1:-}"
[[ -f "$SRC" ]] || { echo "usage: $0 <source-video>" >&2; exit 2; }
command -v ffmpeg >/dev/null || { echo "ffmpeg is required" >&2; exit 2; }

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${OUT_DIR:-$ROOT/frontend/public/media}"
MAX_BYTES=$((6 * 1024 * 1024))
DURATION="${DURATION:-20}"       # seconds kept; a short loop is plenty for a hero background
WIDTH="${WIDTH:-1280}"
mkdir -p "$OUT"

size() { stat -c %s "$1" 2>/dev/null || stat -f %z "$1"; }

encode_mp4() {   # crf rises until the file fits
  for crf in 26 28 30 32 34 36; do
    ffmpeg -y -loglevel error -i "$SRC" -t "$DURATION" -an -vf "scale=${WIDTH}:-2,fps=24" \
      -c:v libx264 -preset slow -crf "$crf" -pix_fmt yuv420p -movflags +faststart "$OUT/hero.mp4"
    [[ $(size "$OUT/hero.mp4") -le $MAX_BYTES ]] && { echo "hero.mp4  crf=$crf  $(size "$OUT/hero.mp4") bytes"; return; }
  done
  echo "WARNING: hero.mp4 is still above 6 MB; lower WIDTH or DURATION" >&2
}
encode_webm() {
  for crf in 34 36 38 40 44; do
    ffmpeg -y -loglevel error -i "$SRC" -t "$DURATION" -an -vf "scale=${WIDTH}:-2,fps=24" \
      -c:v libvpx-vp9 -b:v 0 -crf "$crf" -row-mt 1 "$OUT/hero.webm"
    [[ $(size "$OUT/hero.webm") -le $MAX_BYTES ]] && { echo "hero.webm crf=$crf  $(size "$OUT/hero.webm") bytes"; return; }
  done
  echo "WARNING: hero.webm is still above 6 MB; lower WIDTH or DURATION" >&2
}

encode_mp4
encode_webm
ffmpeg -y -loglevel error -i "$SRC" -frames:v 1 -vf "scale=${WIDTH}:-2" -q:v 4 "$OUT/hero-poster.jpg"
echo "hero-poster.jpg $(size "$OUT/hero-poster.jpg") bytes"

cat > "$OUT/manifest.json" <<JSON
{
  "_comment": "Written by scripts/prepare_media.sh. false = use the procedural WebGL/SVG scene.",
  "hero": { "mp4": true, "webm": true, "poster": true }
}
JSON
echo "manifest updated. Add the clip's licence to $OUT/CREDITS.md before committing."
