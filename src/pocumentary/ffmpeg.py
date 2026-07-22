"""Pure ffmpeg CLI construction and device-list parsing (the pure half of N9).

Mirrors the invocation from docs/reference/fastmcp-cand003/record_cand003.applescript's
startRecording handler, but as an argv list rather than a shell string, so paths
with spaces need no quoting and no shell is involved.

The reference hard-coded FFMPEG_AVFOUNDATION_SCREEN_INDEX=3 with the comment
"this host: [3] Capture screen 0" — exactly the per-host discovery this module
replaces.
"""
from __future__ import annotations

import re

# `ffmpeg -f avfoundation -list_devices true -i ""` prints its inventory to
# stderr and then exits NON-ZERO ("Error opening input file ."). Callers must
# read stderr and ignore the return code.
LIST_DEVICES_ARGS = ["-f", "avfoundation", "-list_devices", "true", "-i", ""]

_VIDEO_HEADER = "AVFoundation video devices:"
_AUDIO_HEADER = "AVFoundation audio devices:"
_DEVICE_RE = re.compile(r"\[(\d+)\]\s+(.+?)\s*$")
_SCREEN_RE = re.compile(r"^Capture screen \d+$")


def parse_avfoundation_devices(stderr: str) -> dict[str, int]:
    """Map video device name -> index from ffmpeg's -list_devices output.

    Only the video section is read. The audio section reuses the same index
    numbers, so running past it would silently produce wrong device indices.
    """
    devices: dict[str, int] = {}
    in_video = False
    for line in stderr.splitlines():
        if _VIDEO_HEADER in line:
            in_video = True
            continue
        if _AUDIO_HEADER in line:
            break
        if not in_video:
            continue
        match = _DEVICE_RE.search(line)
        if match:
            devices[match.group(2)] = int(match.group(1))
    return devices


def find_screen_device(devices: dict[str, int]) -> int:
    """Index of the lowest-numbered 'Capture screen N' device."""
    screens = [idx for name, idx in devices.items() if _SCREEN_RE.match(name)]
    if not screens:
        raise LookupError(
            "no 'Capture screen' device in ffmpeg's avfoundation device list; "
            "grant Screen Recording permission to your terminal in "
            "System Settings > Privacy & Security > Screen Recording"
        )
    return min(screens)


def build_ffmpeg_args(
    device_index: int,
    fps: int,
    crop_filter: str | None,
    out_path: str,
    ffmpeg: str = "ffmpeg",
) -> list[str]:
    """Assemble the screen-capture argv. `<index>:none` means video, no audio."""
    args = [
        ffmpeg,
        "-hide_banner",
        "-f",
        "avfoundation",
        "-framerate",
        str(fps),
        "-i",
        f"{device_index}:none",
    ]
    if crop_filter:
        args += ["-vf", crop_filter]
    args += ["-pix_fmt", "yuv420p", "-y", out_path]
    return args
