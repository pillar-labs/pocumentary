"""Screen-geometry detection (N3): a pure parser + a thin osascript wrapper."""
from __future__ import annotations

import sys
from dataclasses import dataclass

from pocumentary.driver import run_jxa, run_process
from pocumentary.ffmpeg import LIST_DEVICES_ARGS, find_screen_device, parse_avfoundation_devices

# The MAIN display's size in points — deliberately NOT Finder's
# 'bounds of window of desktop', which returns the UNION of every attached
# display. On a multi-monitor Mac that union would tile the panes across
# screens and blow up the auto-crop; a recording targets one display.
_MAIN_SCREEN_SIZE_SCRIPT = (
    "ObjC.import('AppKit'); "
    "var s = $.NSScreen.mainScreen.frame.size; "
    "Math.round(s.width) + ',' + Math.round(s.height)"
)


@dataclass(frozen=True)
class Geometry:
    width_pt: int
    height_pt: int


def parse_screen_size(output: str) -> tuple[int, int]:
    """Parse JXA 'width,height' main-screen size into (width, height) in points."""
    parts = [p.strip() for p in output.strip().split(",")]
    if len(parts) != 2:
        raise ValueError(f"expected 'width,height', got: {output!r}")
    width, height = (int(float(p)) for p in parts)
    return width, height


def detect_geometry() -> Geometry:
    """Point size of the MAIN display (the one carrying the menu bar).

    Uses NSScreen.mainScreen, not the desktop union, so panes tile on a single
    screen and the auto-crop matches that screen — correct on multi-display hosts.
    """
    if sys.platform != "darwin":
        raise RuntimeError("geometry detection requires macOS")
    result = run_jxa(_MAIN_SCREEN_SIZE_SCRIPT)
    if result.returncode != 0:
        raise RuntimeError(f"osascript failed: {result.stderr.strip()}")
    width, height = parse_screen_size(result.stdout)
    return Geometry(width_pt=width, height_pt=height)


_SCALE_SCRIPT = "ObjC.import('AppKit'); $.NSScreen.mainScreen.backingScaleFactor"


def parse_scale(output: str) -> int:
    """Parse a backing scale factor ('2' or '2.0') into an int. Pure."""
    text = output.strip()
    try:
        value = float(text)
    except ValueError:
        raise ValueError(f"could not read backing scale factor from: {output!r}") from None
    if value < 1:
        raise ValueError(f"implausible backing scale factor: {value}")
    return round(value)


def detect_scale() -> int:
    """Points-to-pixels multiplier for the main display (2 on Retina, 1 otherwise)."""
    if sys.platform != "darwin":
        raise RuntimeError("scale detection requires macOS")
    result = run_jxa(_SCALE_SCRIPT)
    if result.returncode != 0:
        raise RuntimeError(f"osascript failed: {result.stderr.strip()}")
    return parse_scale(result.stdout)


def detect_screen_device_index(ffmpeg: str = "ffmpeg") -> int:
    """Find the avfoundation index of the screen-capture device.

    `ffmpeg -list_devices true` always exits non-zero after printing its
    inventory to stderr, so the return code is deliberately ignored.
    """
    try:
        result = run_process([ffmpeg, *LIST_DEVICES_ARGS])
    except FileNotFoundError:
        raise RuntimeError(
            f"ffmpeg not found: {ffmpeg!r}. Install it (brew install ffmpeg) "
            "or set [recording] ffmpeg in your demo.toml"
        ) from None
    return find_screen_device(parse_avfoundation_devices(result.stderr))
