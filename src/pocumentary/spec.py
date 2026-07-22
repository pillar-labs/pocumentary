"""Pure spec model, TOML parsing (N1) and validation (N2). No I/O, no screen."""
from __future__ import annotations

import math
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


class SpecError(Exception):
    """Raised when demo.toml is malformed or missing required structure."""


@dataclass(frozen=True)
class Recording:
    fps: int = 30
    out: str = "recording-{stamp}.mov"
    crop: str = "auto"  # "auto" | "none" | "W:H:X:Y"
    hold: float = 6.0  # seconds to keep recording after the last pane finishes
    step_delay: float = 0.0  # baked into every pane as DEMO_STEP_DELAY (R2 pacing)
    keep: int = 0  # takes to retain when pruning; 0 = keep all
    gate_timeout: float = 60.0  # seconds to wait for any one gate signal


@dataclass(frozen=True)
class Layout:
    mode: str  # "columns" | "rows" | "grid"


@dataclass(frozen=True)
class Pane:
    title: str
    cmd: str
    env: dict[str, str] = field(default_factory=dict)
    cwd: str | None = None
    delay: float = 0.0  # seconds to wait after opening this pane before the next
    gate_on: str | None = None  # signal this pane waits for (consumed in V4)
    signals: tuple[str, ...] = ()  # signals this pane emits (consumed in V4)
    target: str = "local"  # "local" | "ssh:<host>" (remote consumed in V6)


@dataclass(frozen=True)
class Verify:
    """The demo's success predicate: handshake files that must exist when it ends."""

    expect: tuple[str, ...] = ()
    timeout: float = 60.0


@dataclass(frozen=True)
class Annotation:
    """An event-anchored caption (R3.3). `on` names WHEN it appears: the literal
    "start", a pane's signal name, or "pane:<title>". Parsed and validated in
    V6.1; rendered to burned subtitles in V6.2/V6.3."""

    on: str
    text: str
    duration: float = 4.0  # seconds the caption stays on screen


@dataclass(frozen=True)
class Tts:
    """ElevenLabs narration config (V7). Consumed by `narrate`; all fields default
    so an empty or absent [tts] block uses a sensible default voice.

    `speed` is passed through to ElevenLabs voice settings (valid range ~0.7–1.2);
    `seed` pins the synthesis for best-effort reproducibility."""

    voice_id: str = "ySr9tfpEeN2Sp5JTEEW1"
    model_id: str = "eleven_multilingual_v2"
    speed: float = 1.0
    seed: int = 42


_OVERLAY_POSITIONS = ("center", "top-left", "top-right", "bottom-left", "bottom-right")


@dataclass(frozen=True)
class Overlay:
    """An event-anchored image/GIF that pops on screen for a while — the "easter
    egg" (e.g. a mind-blown GIF at the moment of exploit). `on` uses the same
    anchors as [[annotation]]; `gif` is a local path (resolved against the
    demo.toml directory) or an http(s) URL fetched at annotate time."""

    on: str
    gif: str
    duration: float = 3.0  # seconds it stays on screen, then off
    scale: float = 0.4  # width as a fraction of the frame (0 < scale <= 1)
    position: str = "center"  # one of _OVERLAY_POSITIONS


@dataclass(frozen=True)
class Spec:
    recording: Recording
    layout: Layout
    panes: tuple[Pane, ...]
    verify: Verify = Verify()
    annotations: tuple[Annotation, ...] = ()  # V6 subtitles (event-anchored captions)
    tts: "Tts | None" = None  # V7 TTS narration config; None => built-in defaults
    overlays: tuple[Overlay, ...] = ()  # V8 event-anchored image/GIF overlays


def _parse_fps(value: object) -> int:
    """Coerce a raw TOML fps value into an int, or raise SpecError.

    Integers pass through as-is (including 0/negative — validate() catches
    those). Integral floats (30.0) are accepted; non-integral floats (29.97)
    and non-numeric values (including bool, which is a subclass of int) are
    rejected with a SpecError naming the offending value.
    """
    if isinstance(value, bool):
        raise SpecError(f"[recording] fps must be an integer, got {value!r}")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        raise SpecError(f"[recording] fps must be a whole number, got {value}")
    raise SpecError(f"[recording] fps must be an integer, got {value!r}")


def _parse_number(value: object, field: str) -> float:
    """Coerce a raw TOML value into a float, or raise SpecError naming the field.

    Accepts ints and floats. Rejects bool (a subclass of int) and everything
    else. Range checks belong in validate(), not here.
    """
    if isinstance(value, bool):
        raise SpecError(f"{field} must be a number, got {value!r}")
    if isinstance(value, (int, float)):
        return float(value)
    raise SpecError(f"{field} must be a number, got {value!r}")


def _parse_int(value: object, field: str) -> int:
    """Coerce a raw TOML value into an int, or raise SpecError naming the field."""
    if isinstance(value, bool):
        raise SpecError(f"{field} must be an integer, got {value!r}")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    raise SpecError(f"{field} must be an integer, got {value!r}")


def _parse_tts(raw: object) -> Tts:
    """Build a Tts from the [tts] table. Unknown keys are a SpecError (matching
    the strictness of the rest of the parser)."""
    if not isinstance(raw, dict):
        raise SpecError("[tts] must be a table")
    allowed = {"voice_id", "model_id", "speed", "seed"}
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise SpecError(f"[tts] unknown key(s): {', '.join(unknown)}")
    d = Tts()
    return Tts(
        voice_id=str(raw.get("voice_id", d.voice_id)),
        model_id=str(raw.get("model_id", d.model_id)),
        speed=_parse_number(raw.get("speed", d.speed), "[tts] speed"),
        seed=_parse_int(raw.get("seed", d.seed), "[tts] seed"),
    )


def parse(toml_text: str) -> Spec:
    """Parse demo.toml text into a Spec. Raises SpecError on structural problems."""
    try:
        data = tomllib.loads(toml_text)
    except tomllib.TOMLDecodeError as e:
        raise SpecError(f"invalid TOML: {e}") from e

    rec = data.get("recording", {})
    recording = Recording(
        fps=_parse_fps(rec.get("fps", 30)),
        out=str(rec.get("out", "recording-{stamp}.mov")),
        crop=str(rec.get("crop", "auto")),
        hold=_parse_number(rec.get("hold", 6.0), "[recording] hold"),
        step_delay=_parse_number(rec.get("step_delay", 0.0), "[recording] step_delay"),
        keep=_parse_int(rec.get("keep", 0), "[recording] keep"),
        gate_timeout=_parse_number(rec.get("gate_timeout", 60.0), "[recording] gate_timeout"),
    )

    layout_raw = data.get("layout")
    if not isinstance(layout_raw, dict) or "mode" not in layout_raw:
        raise SpecError("missing [layout] table with a 'mode' key")
    layout = Layout(mode=str(layout_raw["mode"]))

    panes: list[Pane] = []
    for i, p in enumerate(data.get("pane", [])):
        if "title" not in p or "cmd" not in p:
            raise SpecError(f"pane #{i + 1}: both 'title' and 'cmd' are required")
        panes.append(
            Pane(
                title=str(p["title"]),
                cmd=str(p["cmd"]),
                env={str(k): str(v) for k, v in p.get("env", {}).items()},
                cwd=(str(p["cwd"]) if "cwd" in p else None),
                delay=_parse_number(p.get("delay", 0.0), f"pane #{i + 1} delay"),
                gate_on=(str(p["gate_on"]) if "gate_on" in p else None),
                signals=tuple(str(s) for s in p.get("signals", [])),
                target=str(p.get("target", "local")),
            )
        )

    verify_raw = data.get("verify", {})
    verify = Verify(
        expect=tuple(str(s) for s in verify_raw.get("expect", [])),
        timeout=_parse_number(verify_raw.get("timeout", 60.0), "[verify] timeout"),
    )

    annotations: list[Annotation] = []
    for i, a in enumerate(data.get("annotation", [])):
        if "on" not in a or "text" not in a:
            raise SpecError(f"annotation #{i + 1}: both 'on' and 'text' are required")
        annotations.append(
            Annotation(
                on=str(a["on"]),
                text=str(a["text"]),
                duration=_parse_number(a.get("duration", 4.0), f"annotation #{i + 1} duration"),
            )
        )

    overlays: list[Overlay] = []
    for i, o in enumerate(data.get("overlay", [])):
        if "on" not in o or "gif" not in o:
            raise SpecError(f"overlay #{i + 1}: both 'on' and 'gif' are required")
        overlays.append(
            Overlay(
                on=str(o["on"]),
                gif=str(o["gif"]),
                duration=_parse_number(o.get("duration", 3.0), f"overlay #{i + 1} duration"),
                scale=_parse_number(o.get("scale", 0.4), f"overlay #{i + 1} scale"),
                position=str(o.get("position", "center")),
            )
        )

    return Spec(
        recording=recording,
        layout=layout,
        panes=tuple(panes),
        verify=verify,
        annotations=tuple(annotations),
        tts=(_parse_tts(data["tts"]) if "tts" in data else None),
        overlays=tuple(overlays),
    )


_VALID_MODES = {"columns", "rows", "grid"}
_CROP_RE = re.compile(r"^\d+:\d+:\d+:\d+$")


def validate(spec: Spec) -> list[str]:
    """Return a list of actionable error messages. Empty list means the spec is valid.

    Structural checks only for now; gate_on/signal cross-referencing lands in V4
    and tts validation lands in V7.
    """
    errors: list[str] = []

    if spec.recording.fps <= 0:
        errors.append(f"[recording] fps must be positive, got {spec.recording.fps}")
    crop = spec.recording.crop
    if crop not in {"auto", "none"} and not _CROP_RE.match(crop):
        errors.append(
            f"[recording] crop must be 'auto', 'none', or 'W:H:X:Y', got {crop!r}"
        )
    if not math.isfinite(spec.recording.hold):
        errors.append(f"[recording] hold must be finite, got {spec.recording.hold}")
    elif spec.recording.hold < 0:
        errors.append(f"[recording] hold must not be negative, got {spec.recording.hold}")
    if not math.isfinite(spec.recording.step_delay):
        errors.append(
            f"[recording] step_delay must be finite, got {spec.recording.step_delay}"
        )
    elif spec.recording.step_delay < 0:
        errors.append(
            f"[recording] step_delay must not be negative, got {spec.recording.step_delay}"
        )
    if not math.isfinite(spec.recording.gate_timeout):
        errors.append(f"[recording] gate_timeout must be finite, got {spec.recording.gate_timeout}")
    elif spec.recording.gate_timeout <= 0:
        errors.append(
            f"[recording] gate_timeout must be positive, got {spec.recording.gate_timeout}"
        )
    if spec.recording.keep < 0:
        errors.append(f"[recording] keep must not be negative, got {spec.recording.keep}")
    out = spec.recording.out
    if Path(out).is_absolute():
        errors.append(f"[recording] out must be a relative path, got {out!r}")
    elif ".." in Path(out).parts:
        errors.append(f"[recording] out must not contain '..' path segments, got {out!r}")

    if spec.layout.mode not in _VALID_MODES:
        errors.append(
            f"[layout] mode must be one of columns|rows|grid, got {spec.layout.mode!r}"
        )

    if not math.isfinite(spec.verify.timeout):
        errors.append(f"[verify] timeout must be finite, got {spec.verify.timeout}")
    elif spec.verify.timeout <= 0:
        errors.append(f"[verify] timeout must be positive, got {spec.verify.timeout}")
    for name in spec.verify.expect:
        if not name.strip():
            errors.append("[verify] expect entries must not be empty")

    if not spec.panes:
        errors.append("at least one [[pane]] is required")

    seen: set[str] = set()
    for i, p in enumerate(spec.panes):
        where = f"[[pane]] #{i + 1} ({p.title!r})"
        if not p.title.strip():
            errors.append(f"[[pane]] #{i + 1}: title must not be empty")
        if not p.cmd.strip():
            errors.append(f"{where}: cmd must not be empty")
        if not math.isfinite(p.delay):
            errors.append(f"{where}: delay must be finite, got {p.delay}")
        elif p.delay < 0:
            errors.append(f"{where}: delay must not be negative, got {p.delay}")
        if p.title in seen:
            errors.append(f"{where}: duplicate title (titles must be unique for cleanup)")
        seen.add(p.title)
        if p.target != "local" and not p.target.startswith("ssh:"):
            errors.append(f"{where}: target must be 'local' or 'ssh:<host>', got {p.target!r}")

    declared_signals = {sig for p in spec.panes for sig in p.signals}
    pane_titles = {p.title for p in spec.panes}
    for i, a in enumerate(spec.annotations):
        where = f"[[annotation]] #{i + 1}"
        if not a.text.strip():
            errors.append(f"{where}: text must not be empty")
        if not math.isfinite(a.duration):
            errors.append(f"{where}: duration must be finite, got {a.duration}")
        elif a.duration <= 0:
            errors.append(f"{where}: duration must be positive, got {a.duration}")
        anchor_ok = (
            a.on == "start"
            or a.on in declared_signals
            or (a.on.startswith("pane:") and a.on[len("pane:") :] in pane_titles)
        )
        if not anchor_ok:
            errors.append(
                f'{where}: on={a.on!r} must be "start", a declared signal, or "pane:<title>"'
            )

    for i, o in enumerate(spec.overlays):
        where = f"[[overlay]] #{i + 1}"
        if not o.gif.strip():
            errors.append(f"{where}: gif must not be empty")
        if not math.isfinite(o.duration):
            errors.append(f"{where}: duration must be finite, got {o.duration}")
        elif o.duration <= 0:
            errors.append(f"{where}: duration must be positive, got {o.duration}")
        if not math.isfinite(o.scale):
            errors.append(f"{where}: scale must be finite, got {o.scale}")
        elif not (0 < o.scale <= 1):
            errors.append(f"{where}: scale must be in (0, 1], got {o.scale}")
        if o.position not in _OVERLAY_POSITIONS:
            errors.append(
                f"{where}: position must be one of {'|'.join(_OVERLAY_POSITIONS)}, "
                f"got {o.position!r}"
            )
        anchor_ok = (
            o.on == "start"
            or o.on in declared_signals
            or (o.on.startswith("pane:") and o.on[len("pane:") :] in pane_titles)
        )
        if not anchor_ok:
            errors.append(
                f'{where}: on={o.on!r} must be "start", a declared signal, or "pane:<title>"'
            )

    if spec.tts is not None:
        if not spec.tts.voice_id.strip():
            errors.append("[tts] voice_id must not be empty")
        if not spec.tts.model_id.strip():
            errors.append("[tts] model_id must not be empty")
        if not math.isfinite(spec.tts.speed):
            errors.append(f"[tts] speed must be finite, got {spec.tts.speed}")
        elif spec.tts.speed <= 0:
            errors.append(f"[tts] speed must be positive, got {spec.tts.speed}")
        if spec.tts.seed < 0:
            errors.append(f"[tts] seed must not be negative, got {spec.tts.seed}")

    from pocumentary.gates import validate_gates  # local import: gates imports Spec from here

    errors.extend(validate_gates(spec))
    return errors
