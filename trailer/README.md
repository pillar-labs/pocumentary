# PoCumentary — release trailer

A ~32s vertical (1080×1920, 30fps) mock-documentary release trailer for PoCumentary,
built with **Remotion** (motion graphics + timing) over clips prepped with **ffmpeg**.
Design spec: [`../docs/superpowers/specs/2026-07-22-pocumentary-release-trailer-design.md`](../docs/superpowers/specs/2026-07-22-pocumentary-release-trailer-design.md).

Delivered artifact: [`../docs/pocumentary-trailer.mp4`](../docs/pocumentary-trailer.mp4).

## Reproduce

```bash
# 1. Assets (git-ignored; regenerate them)
#    - source clips IMG_41xx.mov live in the repo root
#    - music.mp3  : yt-dlp -x --audio-format mp3 'https://www.youtube.com/watch?v=-FEAqmGUjYk'
#    - logo       : cp ../docs/pocumentary_logo.png public/pocumentary_logo.png
#    place music.mp3 at public/music.mp3

# 2. Prep the source clips -> exact 1080x1920/30fps segments in public/clips/
bash scripts/prep.sh

# 3. Install + render
npm install
./node_modules/.bin/remotion render Trailer out/pocumentary-trailer.mp4
# or edit live:
./node_modules/.bin/remotion studio

# 4. Master (true-peak limit so the summed VO+music can't clip) -> delivered file
bash scripts/master.sh
cp out/pocumentary-trailer-master.mp4 ../docs/pocumentary-trailer.mp4
```

The spoken beats are cleaned up in `scripts/prep.sh` (RNN denoise blended 82% wet +
gentle compressor + loudnorm — enough to lift room noise without hollowing the voice).

## How it's wired

- **`src/edl.ts`** — the single source of truth: clip in/out (as frame counts of the
  pre-trimmed segments), the timeline order + crossfades, overlay frame-windows (`M`), and
  all on-screen copy (`COPY`). Re-time or re-word here; footage never has to change.
- **`scripts/prep.sh`** — trims/rotates/scales/loudness-normalizes the 4K source into the
  segments `edl.ts` references. The only stage that touches the heavy source files.
- **`src/Trailer.tsx`** — the timeline: a `TransitionSeries` of the clips (music-bed ducking
  under the VO) plus the overlay layers.
- **`src/components/`** — `Chyron`, `KineticCaption`, `LogoOverlay`, `Letterbox`, `Grade`,
  `Grain`, `PillarMark`. **`src/beats/CTA.tsx`** — the end card.
- **`src/theme.ts`** — Pillar brand tokens (red `#F74A53`, warm canvas `#F6F0F1`, navy ink)
  and fonts (Poppins / Lato / Fira Code).

Beats: sit-down montage → "are they listening?" → the problem (`this many PoCs` / `racking up
vulnerabilities`) → **PoC or GTFO** → the release (logo pops on the word "PoCumentary") → CTA.
