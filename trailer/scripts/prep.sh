#!/usr/bin/env bash
# Prep source clips into exact, trailer-ready 1080x1920/30fps segments.
# Each row of the EDL below is trimmed, autorotated (source carries -90 rotation),
# scaled to 1080x1920, and (for talking beats) loudness-normalized. Sit-down B-roll
# is stripped of audio (-an). Output lands in trailer/public/clips/.
#
# Deterministic: same inputs -> same outputs. This is the only stage that touches
# the heavy 4K source files. Re-run any time the EDL changes.
set -euo pipefail

cd "$(dirname "$0")/.."                 # trailer/
SRC=".."                               # repo root (IMG_41xx.mov live here)
OUT="public/clips"
mkdir -p "$OUT"

FPS=30

# Voice chain for the spoken beats: light touch — clean up a little without any
# "processed"/hollow character.
#  highpass      - drop only sub-60Hz rumble (keeps low-end warmth)
#  arnndn mix=.6 - RNN speech denoise blended just 60% wet, so most of the natural
#                  voice passes through untouched (the denoiser's own coloration is
#                  what reads as hollow, so we lean on it lightly)
#  acompressor   - very gentle levelling
#  loudnorm      - consistent broadcast level
MODEL="scripts/denoise.rnnn"
VOICE="highpass=f=60,arnndn=m=${MODEL}:mix=0.6,acompressor=threshold=-19dB:ratio=2.2:attack=25:release=250:makeup=1.5,loudnorm=I=-16:TP=-1.5:LRA=11"

# name              src            in     out    audio(1/0)
EDL=(
  "s1_sit           IMG_4151.mov   1.60   3.90   0"   # empty beat -> walks into frame (breathe)
  "s2_sit           IMG_4150.mov   2.30   4.60   0"   # bends to set the laptop down
  "s3_sit           IMG_4158.mov   0.00   2.10   0"   # lowering into the seat
  "s4_sit           IMG_4149.mov   3.60   6.00   0"   # settles, holds -> cuts to the interview
  "listen           IMG_4155.mov   0.00   3.20   1"   # "what they know. oh boy."
  "prob_cursor      IMG_4150.mov   9.20   12.60  1"   # "this cursor here, our codex here"
  "prob_a           IMG_4153.mov   0.80   9.55   1"   # "...racking up the vulnerabilities" + breath
  "prob_gtfo        IMG_4153.mov   22.30  25.30  1"   # "it's either PoC or GTFO"
  "reveal_a         IMG_4158.mov   2.60   6.20   1"   # "today we're releasing our PoCumentary tool"
  "reveal_b         IMG_4158.mov   14.10  20.95  1"   # "give back to the community... exploits you found" + breath
)

for row in "${EDL[@]}"; do
  read -r name src tin tout aud <<<"$row"
  dur=$(python3 -c "print(round($tout-$tin,3))")
  echo ">> $name  <- $src  [$tin..$tout] ${dur}s  audio=$aud"
  if [ "$aud" = "1" ]; then
    ffmpeg -y -ss "$tin" -to "$tout" -i "$SRC/$src" \
      -vf "scale=1080:1920:flags=lanczos,fps=$FPS,setsar=1" \
      -af "${VOICE},afade=t=in:st=0:d=0.04,afade=t=out:st=$(python3 -c "print(round($dur-0.06,3))"):d=0.06" \
      -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p \
      -c:a aac -b:a 192k -ar 48000 \
      "$OUT/$name.mp4" -loglevel error
  else
    ffmpeg -y -ss "$tin" -to "$tout" -i "$SRC/$src" \
      -vf "scale=1080:1920:flags=lanczos,fps=$FPS,setsar=1" \
      -an \
      -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p \
      "$OUT/$name.mp4" -loglevel error
  fi
done

echo "=== prepped segments ==="
for f in "$OUT"/*.mp4; do
  printf "%-28s %s\n" "$f" "$(ffprobe -v error -select_streams v:0 -show_entries stream=width,height,nb_frames -of csv=p=0 "$f")"
done
