"""Pure crop-region math (N5): pane bounds in points -> an ffmpeg crop filter.

Reproduces the hand-derived `DEMO_CROP=crop=3024:1884:0:60` from
docs/reference/fastmcp-cand003/run_recording.sh, which was discovered by trial
and error per host. Here it falls out of the layout solver instead.

The full-tile + crop approach is the shipping isolation strategy (shaping R8.2
was demoted): record the whole screen, then crop to exactly the region the panes
occupy, so the menu bar, Dock, and everything else stay out of the frame.
"""
from __future__ import annotations

from dataclasses import dataclass

from pocumentary.layout import Bounds


@dataclass(frozen=True)
class Crop:
    """An ffmpeg crop rectangle in *pixels*."""

    width: int
    height: int
    x: int
    y: int

    def to_filter(self) -> str:
        return f"crop={self.width}:{self.height}:{self.x}:{self.y}"


def _floor_even(n: int) -> int:
    """Round down to the nearest even number.

    -pix_fmt yuv420p subsamples chroma 2x2, so libx264 refuses odd dimensions
    with "Could not open encoder before EOF". Losing at most one pixel per axis
    is invisible; failing the take is not.
    """
    return n - (n % 2)


def crop_region(bounds: list[Bounds], scale: int) -> Crop:
    """Bounding box of every pane, converted from points to pixels."""
    if not bounds:
        raise ValueError("crop needs at least one pane's bounds")

    x1 = min(b[0] for b in bounds)
    y1 = min(b[1] for b in bounds)
    x2 = max(b[2] for b in bounds)
    y2 = max(b[3] for b in bounds)

    return Crop(
        width=_floor_even((x2 - x1) * scale),
        height=_floor_even((y2 - y1) * scale),
        x=x1 * scale,
        y=y1 * scale,
    )


def resolve_crop(spec_crop: str, bounds: list[Bounds], scale: int) -> str | None:
    """Turn the spec's `[recording] crop` setting into an ffmpeg -vf value.

    "none" -> None (record the full screen); "auto" -> the computed region;
    "W:H:X:Y" -> the author's literal override, passed through untouched.
    The spec's validate() has already rejected any other shape.
    """
    if spec_crop == "none":
        return None
    if spec_crop == "auto":
        return crop_region(bounds, scale).to_filter()
    return f"crop={spec_crop}"
