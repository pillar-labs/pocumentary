"""Pure image/GIF-overlay substrate (V8). No I/O, no screen, no network.

The "easter egg" sibling of subtitles.py: it turns event-anchored [[overlay]]
blocks plus a captured timeline into placements (when each GIF pops on, for how
long, how big, where) and the ffmpeg filtergraph/argv that burns them onto a
take. The effects — downloading a URL and running ffmpeg — live in cli.py and
postprod.py.

A GIF loops for its whole on-screen window via ffmpeg's `-ignore_loop 0` on the
image input; `overlay=...:enable='between(t,start,end)'` shows it only within
the window. Each GIF is sized to a fraction of the frame width with `scale2ref`
(aspect preserved) so it looks the same regardless of the recording's resolution.

Path math uses os.path (not pathlib.Path) so the module stays clear of the pure
grep set's pathlib marker — the same choice subtitles.py and gates.py make.
"""
from __future__ import annotations

from dataclasses import dataclass

from pocumentary.spec import Overlay


class OverlayError(Exception):
    """Raised when an overlay anchors to an event absent from the timeline."""


@dataclass(frozen=True)
class Placement:
    """One GIF placed on the recording's clock.

    `gif` is the spec's unresolved reference (a path or URL) — the caller resolves
    it to a local file before building argv. `start`/`duration` frame the on-screen
    window; `scale` is the width as a fraction of the frame; `position` is one of
    the spec's named anchors.
    """

    gif: str
    start: float
    duration: float
    scale: float
    position: str


# overlay expressions: W/H are the main (base) frame, w/h the scaled GIF.
_POSITION_XY = {
    "center": ("(W-w)/2", "(H-h)/2"),
    "top-left": ("0", "0"),
    "top-right": ("W-w", "0"),
    "bottom-left": ("0", "H-h"),
    "bottom-right": ("W-w", "H-h"),
}


def build_placements(
    overlays: tuple[Overlay, ...], timeline: dict[str, float]
) -> list[Placement]:
    """Resolve overlays against a captured timeline into ordered Placements.

    Sorted by start offset (ties keep declaration order — Python sort is stable).
    Raises OverlayError — naming every offender — if any overlay anchors to an
    event absent from the timeline. Returns [] when there are no overlays.
    """
    missing = sorted({o.on for o in overlays if o.on not in timeline})
    if missing:
        raise OverlayError(
            "no timeline entry for overlay anchor(s): "
            + ", ".join(repr(m) for m in missing)
        )
    ordered = sorted(overlays, key=lambda o: timeline[o.on])
    return [
        Placement(
            gif=o.gif,
            start=timeline[o.on],
            duration=o.duration,
            scale=o.scale,
            position=o.position,
        )
        for o in ordered
    ]


def _num(value: float) -> str:
    """Render a float for an ffmpeg expression without scientific notation."""
    return f"{value:.6f}".rstrip("0").rstrip(".")


def final_label(placements: list[Placement]) -> str:
    """The filtergraph label to `-map` — the last stage's video output, `[vN]`."""
    if not placements:
        raise ValueError("no placements")
    return f"[v{len(placements) - 1}]"


def overlay_filter(placements: list[Placement]) -> str:
    """Build the filter_complex that scales and time-gates each GIF in turn.

    Input 0 is the base video; inputs 1..N are the GIFs in `placements` order.
    Each GIF is scaled to `scale * frame_width` (aspect preserved) then overlaid
    for its window; the result feeds the next stage. The graph's final output is
    labelled `[vN]` (see final_label). Raises ValueError on an empty list.
    """
    if not placements:
        raise ValueError("overlay_filter needs at least one placement")
    segments: list[str] = []
    prev = "0:v"
    for i, p in enumerate(placements):
        gif_in = f"{i + 1}:v"
        g, base, vout = f"g{i}", f"b{i}", f"v{i}"
        s = _num(p.scale)
        # scale the GIF to s*main_w, keeping its own aspect (ih/iw); ref is the
        # running base video, which scale2ref passes through unchanged as [base].
        segments.append(
            f"[{gif_in}][{prev}]scale2ref=w='main_w*{s}':h='main_w*{s}*ih/iw'[{g}][{base}]"
        )
        x, y = _POSITION_XY[p.position]
        end = _num(p.start + p.duration)
        segments.append(
            f"[{base}][{g}]overlay=x={x}:y={y}:"
            f"enable='between(t,{_num(p.start)},{end})'[{vout}]"
        )
        prev = vout
    return ";".join(segments)


def overlay_args(
    mov_path: str,
    gif_paths: list[str],
    placements: list[Placement],
    out_path: str,
    ffmpeg: str = "ffmpeg",
    max_duration: float | None = None,
) -> list[str]:
    """ffmpeg argv that burns each (looping) GIF onto `mov_path` -> `out_path`.

    `gif_paths` are resolved LOCAL files, one per placement in the same order.
    Video is re-encoded because the overlay rasterises into the pixels; the take
    is silent, so no audio is mapped (matching the subtitle burn).

    Runaway guard (both belt AND suspenders — a looping GIF once drove ffmpeg to
    a disk-filling 18 GB encode):
      1. Each `-ignore_loop 0` GIF input is bounded with `-t` to the END of its
         on-screen window (start + duration), so an infinite image input can
         never drive an unbounded output. The GIF still loops for its whole
         window; it just stops being read afterwards.
      2. When `max_duration` is given (the source take's real length), the OUTPUT
         is capped with `-t` so the result can never be longer than the source.
    """
    if len(gif_paths) != len(placements):
        raise ValueError("gif_paths and placements must be the same length")
    graph = overlay_filter(placements)
    args = [ffmpeg, "-hide_banner", "-i", mov_path]
    for gif, p in zip(gif_paths, placements):
        window_end = _num(p.start + p.duration)
        args += ["-ignore_loop", "0", "-t", window_end, "-i", gif]
    args += [
        "-filter_complex", graph,
        "-map", final_label(placements),
        "-pix_fmt", "yuv420p",
    ]
    if max_duration is not None:
        args += ["-t", _num(max_duration)]
    args += ["-y", out_path]
    return args
