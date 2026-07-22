"""Pure narration substrate (N17, A7). No I/O, no screen.

Two consumers share this module: `annotate` (render side — a captured timeline
plus the [[annotation]] blocks -> SRT text and the ffmpeg burn argv) and, in
V6.3, `record` (capture side — which events to watch and how to serialize the
timeline). Keeping it all pure makes the whole subtitle pipeline unit-testable
without a screen or a real recording; the effects (running ffmpeg, polling the
filesystem) live in postprod.py and record.py.

Path math uses os.path (not pathlib.Path) so the module stays clear of the pure
grep set's pathlib marker — the same choice gates.py makes with os.path.join.
"""
from __future__ import annotations

import json
import os.path

from pocumentary.gates import signal_path
from pocumentary.spec import Annotation, Spec


class SubtitleError(Exception):
    """Raised when a timeline is malformed, or an annotation anchors to an event
    that never occurred in the recorded take (e.g. a signal that never fired)."""


def _srt_timestamp(seconds: float) -> str:
    """Format seconds as an SRT timestamp `HH:MM:SS,mmm`. Negatives clamp to 0."""
    if seconds < 0:
        seconds = 0.0
    ms_total = int(round(seconds * 1000))
    hours, ms_total = divmod(ms_total, 3_600_000)
    minutes, ms_total = divmod(ms_total, 60_000)
    secs, ms = divmod(ms_total, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def build_srt(annotations: tuple[Annotation, ...], timeline: dict[str, float]) -> str:
    """Render event-anchored annotations to SRT text against a captured timeline.

    Each annotation becomes one cue: start = timeline[on], end = start + duration.
    Cues are sorted by start (ties by end) and numbered from 1. Raises
    SubtitleError — naming every offender — if any annotation anchors to an event
    absent from the timeline. Returns "" when there are no annotations.
    """
    missing = sorted({a.on for a in annotations if a.on not in timeline})
    if missing:
        raise SubtitleError(
            "no timeline entry for annotation anchor(s): "
            + ", ".join(repr(m) for m in missing)
        )
    cues = sorted(
        ((timeline[a.on], timeline[a.on] + a.duration, a.text) for a in annotations),
        key=lambda c: (c[0], c[1]),
    )
    blocks = [
        f"{n}\n{_srt_timestamp(start)} --> {_srt_timestamp(end)}\n{text}\n"
        for n, (start, end, text) in enumerate(cues, start=1)
    ]
    return "\n".join(blocks)


def load_timeline(json_text: str) -> dict[str, float]:
    """Parse `<out>.timeline.json` text into an event -> offset map.

    Raises SubtitleError on anything that is not a JSON array of {event, offset}.
    """
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as e:
        raise SubtitleError(f"invalid timeline JSON: {e}") from e
    if not isinstance(data, list):
        raise SubtitleError("timeline must be a JSON array of {event, offset}")
    timeline: dict[str, float] = {}
    for i, item in enumerate(data):
        if not isinstance(item, dict) or "event" not in item or "offset" not in item:
            raise SubtitleError(f"timeline entry #{i + 1} needs 'event' and 'offset'")
        offset = item["offset"]
        if isinstance(offset, bool) or not isinstance(offset, (int, float)):
            raise SubtitleError(f"timeline entry #{i + 1}: offset must be a number")
        timeline[str(item["event"])] = float(offset)
    return timeline


def captioned_out_path(mov_path: str) -> str:
    """`.../recording.mov` -> `.../recording-captioned.mov` (a sibling file)."""
    root, ext = os.path.splitext(mov_path)
    return f"{root}-captioned{ext}"


# libass style: white text, semi-transparent box, bottom-margin — legible on any
# background (R3.3d). BorderStyle=3 draws the box; MarginV lifts it off the edge.
_FORCE_STYLE = (
    "FontName=Helvetica,FontSize=22,PrimaryColour=&H00FFFFFF&,"
    "BorderStyle=3,BackColour=&H80000000&,Outline=0,Shadow=0,MarginV=40"
)


def _escape_subtitles_path(path: str) -> str:
    """Escape a filename for the ffmpeg `subtitles` filter value.

    Inside a filtergraph `\\`, `:` and `'` are special. pocumentary always hands this
    a tool-generated temp path (simple chars in practice), but escaping keeps the
    argv correct regardless.
    """
    return path.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def burn_args(
    mov_path: str, srt_path: str, out_path: str, ffmpeg: str = "ffmpeg"
) -> list[str]:
    """ffmpeg argv that burns `srt_path` into `mov_path` -> `out_path`.

    Uses the libass `subtitles` filter (confirmed in the shipping ffmpeg 7.1.1,
    see docs/spike-v6-subtitle-timeline.md). The recording carries no audio
    track, so no audio mapping is needed; video is re-encoded because the filter
    rasterises the text into the pixels (R3.3d — one shareable artifact).
    """
    vf = f"subtitles='{_escape_subtitles_path(srt_path)}':force_style='{_FORCE_STYLE}'"
    return [
        ffmpeg,
        "-hide_banner",
        "-i",
        mov_path,
        "-vf",
        vf,
        "-pix_fmt",
        "yuv420p",
        "-y",
        out_path,
    ]


MARKER_PREFIX = ".pocumentary-open-"  # per-pane window-open marker, index-suffixed
START_EVENT = "start"


def marker_path(runtime_dir: str, index: int) -> str:
    """Path of the window-open marker for pane `index` (0-based).

    `record`'s generated AppleScript touches this right after the pane's window
    opens; the timeline poller watches for it. A leading dot + fixed prefix keeps
    it from ever colliding with an author's signal name.
    """
    return signal_path(runtime_dir, f"{MARKER_PREFIX}{index}")


def pane_event(title: str) -> str:
    """The timeline/anchor event name for a pane opening: `pane:<title>`."""
    return f"pane:{title}"


def timeline_watches(spec: Spec, runtime_dir: str) -> dict[str, str]:
    """Map each watchable event -> the file whose first appearance times it.

    Covers every pane-open marker (`pane:<title>`) and every declared signal. The
    synthetic `start` event is NOT here — it is not a file; build_timeline_json
    injects it at offset 0.0.
    """
    watches: dict[str, str] = {}
    for i, pane in enumerate(spec.panes):
        watches[pane_event(pane.title)] = marker_path(runtime_dir, i)
    for pane in spec.panes:
        for sig in pane.signals:
            watches[sig] = signal_path(runtime_dir, sig)
    return watches


def build_timeline_json(offsets: dict[str, float]) -> str:
    """Serialize captured event offsets to `<out>.timeline.json` text.

    Always injects `start` at 0.0 (video t=0). Entries are sorted by offset (ties
    by event name) so the sidecar reads chronologically. Pure — the caller writes
    the file.
    """
    merged = {START_EVENT: 0.0, **offsets}
    entries = [
        {"event": event, "offset": offset}
        for event, offset in sorted(merged.items(), key=lambda kv: (kv[1], kv[0]))
    ]
    return json.dumps(entries, indent=2) + "\n"
