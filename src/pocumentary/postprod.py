"""Post-production caption burn (N14, A7). Effect edge — NOT in the pure set.

The pure SRT/argv construction lives in subtitles.py; this module is only the
thin effect that writes the SRT to disk (the `subtitles` filter needs a real
path) and shells out to ffmpeg, exactly as record.py shells out for capture.
"""
from __future__ import annotations

import os
import subprocess
import tempfile

from pocumentary.narration import mix_args
from pocumentary.overlay import Placement, overlay_args
from pocumentary.subtitles import burn_args


class PostprodError(Exception):
    """Raised when the caption burn cannot run or ffmpeg reports failure."""


def _probe_duration(mov_path: str, ffprobe: str) -> float | None:
    """Best-effort real duration of `mov_path` in seconds, via ffprobe.

    Returns None (never raises) if ffprobe is missing or cannot read the file —
    the caller uses it only as a hard OUTPUT cap, and the per-GIF `-t` bounds
    already prevent a runaway even without it.
    """
    try:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", mov_path],
            capture_output=True, text=True,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def burn_overlays(
    mov_path: str,
    gif_paths: list[str],
    placements: list[Placement],
    out_path: str,
    ffmpeg: str = "ffmpeg",
    ffprobe: str = "ffprobe",
) -> None:
    """Burn each (looping) GIF in `placements` onto `mov_path` -> `out_path`.

    `gif_paths` are resolved local files, one per placement in order (the caller
    downloads any URLs first). The output is hard-capped to the source take's
    length (probed with ffprobe) so a looping GIF can never produce a runaway
    encode. Raises PostprodError on any ffmpeg failure, surfacing its stderr tail.
    """
    max_duration = _probe_duration(mov_path, ffprobe)
    args = overlay_args(mov_path, gif_paths, placements, out_path, ffmpeg, max_duration)
    try:
        result = subprocess.run(args, capture_output=True, text=True)
    except FileNotFoundError as e:
        raise PostprodError(
            f"ffmpeg not found: {ffmpeg!r}. Install it with: brew install ffmpeg"
        ) from e
    except OSError as e:
        raise PostprodError(f"could not run ffmpeg: {e}") from e
    if result.returncode != 0:
        tail = "\n".join(result.stderr.strip().splitlines()[-15:])
        raise PostprodError(f"ffmpeg failed to burn overlays:\n{tail}")


def burn_subtitles(
    mov_path: str, srt_text: str, out_path: str, ffmpeg: str = "ffmpeg"
) -> None:
    """Burn `srt_text` onto `mov_path`, writing `out_path`.

    Raises PostprodError on any failure, surfacing ffmpeg's own stderr when it is
    the culprit. The SRT is written to a private temp file and removed afterwards;
    ffmpeg's combined output is captured so a failure is actionable rather than
    lost to the console.
    """
    fd, srt_path = tempfile.mkstemp(prefix="pocumentary-", suffix=".srt")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(srt_text)
        args = burn_args(mov_path, srt_path, out_path, ffmpeg)
        try:
            result = subprocess.run(args, capture_output=True, text=True)
        except FileNotFoundError as e:
            raise PostprodError(
                f"ffmpeg not found: {ffmpeg!r}. Install it with: brew install ffmpeg"
            ) from e
        except OSError as e:
            raise PostprodError(f"could not run ffmpeg: {e}") from e
        if result.returncode != 0:
            tail = "\n".join(result.stderr.strip().splitlines()[-15:])
            raise PostprodError(f"ffmpeg failed to burn captions:\n{tail}")
    finally:
        try:
            os.remove(srt_path)
        except OSError:
            pass


def mix_narration(
    mov_path: str,
    clip_paths: list[str],
    offsets: list[float],
    out_path: str,
    ffmpeg: str = "ffmpeg",
) -> None:
    """Delay each clip to its offset, mix into one track, mux onto `mov_path`.

    Raises PostprodError on any failure, surfacing ffmpeg's own stderr tail. No
    temp files: the clips already exist on disk (synth.py wrote them) and are the
    caller's to clean up. Video is copied, so this is fast and lossless.
    """
    args = mix_args(mov_path, clip_paths, offsets, out_path, ffmpeg)
    try:
        result = subprocess.run(args, capture_output=True, text=True)
    except FileNotFoundError as e:
        raise PostprodError(
            f"ffmpeg not found: {ffmpeg!r}. Install it with: brew install ffmpeg"
        ) from e
    except OSError as e:
        raise PostprodError(f"could not run ffmpeg: {e}") from e
    if result.returncode != 0:
        tail = "\n".join(result.stderr.strip().splitlines()[-15:])
        raise PostprodError(f"ffmpeg failed to mix narration:\n{tail}")
