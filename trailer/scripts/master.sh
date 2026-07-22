#!/usr/bin/env bash
# Final master: guarantee no clipping. Remotion sums the VO and music tracks with
# no master-bus limiter, so their transients can stack to full scale. This pass
# loudness-normalizes the mixed audio to a web target with a true-peak ceiling and
# copies the video stream untouched.
set -euo pipefail
cd "$(dirname "$0")/.."   # trailer/

IN="${1:-out/pocumentary-trailer.mp4}"
OUT="${2:-out/pocumentary-trailer-master.mp4}"

ffmpeg -y -i "$IN" \
  -c:v copy \
  -af "loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000" \
  -c:a aac -b:a 256k \
  "$OUT" -loglevel error

echo "mastered -> $OUT"
ffmpeg -hide_banner -i "$OUT" -af volumedetect -f null /dev/null 2>&1 | grep -E "mean_volume|max_volume"
