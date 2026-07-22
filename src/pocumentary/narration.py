"""Pure TTS-narration substrate (N14/A7.4). No I/O, no engine, no screen.

The V7 sibling of subtitles.py: it turns the event-anchored [[annotation]]
sections plus a captured timeline into ordered narration Sections (each with the
time until the next event), the ffmpeg argv that mixes the synthesized clips onto
the recording, and the length checks. The effects — running the TTS engine and
ffmpeg — live in synth.py and postprod.py.

Path math uses os.path (not pathlib.Path) so the module stays clear of the pure
grep set's pathlib marker — the same choice gates.py and subtitles.py make.
"""
from __future__ import annotations

import math
import os.path
from dataclasses import dataclass

from pocumentary.spec import Annotation, Spec

CHARS_PER_SECOND = 11  # spike calibration: ~40-char lines synth to ~3.7-4.0 s


class NarrationError(Exception):
    """Raised when an annotation anchors to an event absent from the timeline."""


@dataclass(frozen=True)
class Section:
    """One narration line placed on the recording's clock.

    `offset` is the event's time into the video (seconds); `slot` is the time
    until the next section's event (math.inf for the last section, which has no
    successor and so can never overrun).
    """

    on: str
    text: str
    offset: float
    slot: float


def narrated_out_path(mov_path: str) -> str:
    """`.../rec.mov` -> `.../rec-narrated.mov` (a sibling file)."""
    root, ext = os.path.splitext(mov_path)
    return f"{root}-narrated{ext}"


def build_sections(
    annotations: tuple[Annotation, ...], timeline: dict[str, float]
) -> list[Section]:
    """Resolve annotations against a captured timeline into ordered Sections.

    Sorted by event offset (ties keep declaration order — Python sort is stable).
    Each section's slot is the gap to the next section's offset; the final
    section's slot is math.inf. Raises NarrationError — naming every offender —
    if any annotation anchors to an event absent from the timeline.
    """
    missing = sorted({a.on for a in annotations if a.on not in timeline})
    if missing:
        raise NarrationError(
            "no timeline entry for annotation anchor(s): "
            + ", ".join(repr(m) for m in missing)
        )
    ordered = sorted(annotations, key=lambda a: timeline[a.on])
    offsets = [timeline[a.on] for a in ordered]
    sections: list[Section] = []
    for i, a in enumerate(ordered):
        slot = (offsets[i + 1] - offsets[i]) if i + 1 < len(ordered) else math.inf
        sections.append(Section(on=a.on, text=a.text, offset=offsets[i], slot=slot))
    return sections


def estimate_speech_seconds(text: str) -> float:
    """A conservative pre-record estimate of spoken length (seconds).

    Deterministic and spec-only (there is no timeline before recording). Rounds
    up at CHARS_PER_SECOND so it errs toward warning — nudging authors to short
    lines. Not authoritative: the real duration is only known after synth.
    """
    return float(math.ceil(len(text) / CHARS_PER_SECOND))


def narration_warnings(spec: Spec) -> list[str]:
    """Advisory warnings: annotations whose estimated speech exceeds their
    declared `duration`. Never blocks — the binding check is overlap_errors,
    post-synth. Returns one message per over-long annotation."""
    warnings: list[str] = []
    for i, a in enumerate(spec.annotations):
        est = estimate_speech_seconds(a.text)
        if est > a.duration:
            warnings.append(
                f"[[annotation]] #{i + 1} (on={a.on!r}): ~{est:.0f}s of speech may "
                f"overrun its {a.duration:g}s duration; shorten the text or raise duration"
            )
    return warnings


def overlap_errors(sections: list[Section], durations: list[float]) -> list[str]:
    """Post-synth hard check: a section whose real clip duration exceeds its slot
    (the time until the next event) would overlap the next line. The final
    section has an infinite slot and never overruns. Returns one message per
    offender; empty means clear."""
    errors: list[str] = []
    for section, duration in zip(sections, durations):
        if duration > section.slot:
            errors.append(
                f"[[annotation]] on={section.on!r}: narration is {duration:.2f}s but only "
                f"{section.slot:.2f}s until the next event; shorten the text"
            )
    return errors


def mix_args(
    mov_path: str,
    clip_paths: list[str],
    offsets: list[float],
    out_path: str,
    ffmpeg: str = "ffmpeg",
) -> list[str]:
    """ffmpeg argv that delays each clip to its offset, mixes them into one track,
    and muxes it onto `mov_path` -> `out_path`.

    The recording is silent, so the whole audio track is built from the clips
    (spike docs/spike-v7-tts.md). Video is COPIED (-c:v copy): unlike the subtitle
    burn, narration only adds an audio stream, so the mux is fast and lossless.
    `adelay` takes milliseconds; `M|M` delays every channel by M (extra channel
    specs are ignored for mono, so this is channel-agnostic).
    """
    delays: list[str] = []
    labels: list[str] = []
    for i, offset in enumerate(offsets, start=1):
        ms = int(round(offset * 1000))
        label = f"a{i}"
        delays.append(f"[{i}:a]adelay={ms}|{ms}[{label}]")
        labels.append(f"[{label}]")
    graph = (
        ";".join(delays)
        + ";"
        + "".join(labels)
        + f"amix=inputs={len(offsets)}:normalize=0[aout]"
    )
    args = [ffmpeg, "-hide_banner", "-i", mov_path]
    for clip in clip_paths:
        args += ["-i", clip]
    args += [
        "-filter_complex", graph,
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy", "-c:a", "aac",
        "-y", out_path,
    ]
    return args
