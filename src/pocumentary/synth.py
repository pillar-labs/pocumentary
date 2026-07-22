"""TTS synthesis (N14/A7.4). Effect edge — NOT pure.

Two backends behind one `synthesize()`:

* **ElevenLabs** (cloud, preferred) when an API key is resolved — higher quality.
* **on-device mlx-audio** (local fallback) when no key is found — no network,
  reproducible via a pinned RNG seed, but lower quality.

`synthesize()` picks the backend from whether `api_key` is truthy. Each engine
is imported LAZILY and nowhere else, so the core package keeps `dependencies = []`
and runs fine without the opt-in extras (`pocumentary[tts]` for ElevenLabs,
`pocumentary[tts-local]` for mlx-audio). The API key is resolved by the caller
(env var or a project `.env`) and passed in — this module never reads credentials.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass

from pocumentary.narration import Section
from pocumentary.spec import Tts

# ElevenLabs returns MP3 at this bitrate/samplerate; ffmpeg reads it directly in
# the mix step and ffprobe reads its duration. mp3 is self-describing, so the
# mixing argv needs no per-input format flags.
_OUTPUT_FORMAT = "mp3_44100_128"

# The on-device fallback voice. The Tts block's voice_id/model_id are ElevenLabs
# identifiers, so the local engine uses its own fixed model and voice; only
# `speed` and `seed` carry over from the spec.
_LOCAL_MODEL = "mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-4bit"
_LOCAL_VOICE = "uncle_fu"


class SynthError(Exception):
    """Raised when the TTS engine is missing or a synthesis call fails."""


@dataclass(frozen=True)
class Clip:
    """A synthesized narration clip on disk plus its measured duration."""

    path: str
    duration: float


def synthesize(
    sections: list[Section], tts: Tts, out_dir: str, api_key: str | None,
    ffprobe: str = "ffprobe",
) -> list[Clip]:
    """Render one clip per section into `out_dir`, returned in section order.

    Uses ElevenLabs when `api_key` is truthy, otherwise falls back to the
    on-device mlx-audio engine. Raises SynthError if the chosen engine is
    absent or a synthesis call fails.
    """
    if api_key:
        return _synthesize_elevenlabs(sections, tts, out_dir, api_key, ffprobe)
    return _synthesize_local(sections, tts, out_dir)


# --- ElevenLabs (cloud) -----------------------------------------------------

def _require_engine():
    """Import the ElevenLabs SDK lazily; on failure raise an actionable error.

    Returns `(ElevenLabs, VoiceSettings)`. Isolated so tests can monkeypatch it
    with fakes instead of installing the SDK or hitting the network.
    """
    try:
        from elevenlabs import VoiceSettings
        from elevenlabs.client import ElevenLabs
    except ImportError as e:
        raise SynthError(
            "ElevenLabs SDK not installed. Install it with: pip install 'pocumentary[tts]'"
        ) from e
    return ElevenLabs, VoiceSettings


def _probe_duration(path: str, ffprobe: str = "ffprobe") -> float:
    """Real duration of an audio file in seconds, via ffprobe.

    Raises SynthError if ffprobe is missing or cannot read the file — the
    overlap guard depends on this number being accurate.
    """
    try:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True,
        )
    except FileNotFoundError as e:
        raise SynthError(
            f"ffprobe not found: {ffprobe!r}. Install it (brew install ffmpeg)"
        ) from e
    if result.returncode != 0:
        raise SynthError(f"ffprobe failed on {path!r}: {result.stderr.strip()}")
    try:
        return float(result.stdout.strip())
    except ValueError as e:
        raise SynthError(f"ffprobe gave no duration for {path!r}") from e


def _synthesize_elevenlabs(
    sections: list[Section], tts: Tts, out_dir: str, api_key: str, ffprobe: str,
) -> list[Clip]:
    """Render each section with ElevenLabs text_to_speech.convert.

    Builds one client and calls convert per section with a pinned `seed`
    (best-effort reproducibility) and the configured voice/model/speed, then
    measures each clip's real duration with ffprobe.
    """
    ElevenLabs, VoiceSettings = _require_engine()
    client = ElevenLabs(api_key=api_key)
    settings = VoiceSettings(speed=tts.speed)

    clips: list[Clip] = []
    for i, section in enumerate(sections):
        try:
            audio = client.text_to_speech.convert(
                text=section.text,
                voice_id=tts.voice_id,
                model_id=tts.model_id,
                output_format=_OUTPUT_FORMAT,
                voice_settings=settings,
                seed=tts.seed,
            )
        except Exception as e:  # noqa: BLE001 - surface any API failure uniformly
            raise SynthError(f"synthesis failed for {section.text!r}: {e}") from e
        path = os.path.join(out_dir, f"clip-{i:03d}.mp3")
        with open(path, "wb") as f:
            for chunk in audio:
                f.write(chunk)
        clips.append(Clip(path=path, duration=_probe_duration(path, ffprobe)))
    return clips


# --- mlx-audio (on-device fallback) -----------------------------------------

def _require_local_engine():
    """Import the on-device mlx-audio engine lazily; on failure raise an
    actionable error. Returns `(mx, load, audio_write)`.
    """
    try:
        import mlx.core as mx
        from mlx_audio.audio_io import write as audio_write
        from mlx_audio.tts import load
    except ImportError as e:
        raise SynthError(
            "No ElevenLabs API key and the on-device engine is not installed. "
            "Set $ELEVENLABS_API_KEY, or install the fallback with: "
            "pip install 'pocumentary[tts-local]'"
        ) from e
    return mx, load, audio_write


def _synthesize_local(sections: list[Section], tts: Tts, out_dir: str) -> list[Clip]:
    """Render each section with the on-device mlx-audio engine.

    Loads the model once and seeds the RNG once (reproducible output). The Tts
    voice_id/model_id are ElevenLabs identifiers, so this fallback uses its own
    fixed model and voice; only `speed` and `seed` carry over.
    """
    mx, load, audio_write = _require_local_engine()
    try:
        model = load(_LOCAL_MODEL)
    except Exception as e:  # noqa: BLE001 - surface any engine load failure uniformly
        raise SynthError(f"could not load TTS model {_LOCAL_MODEL!r}: {e}") from e
    mx.random.seed(tts.seed)

    clips: list[Clip] = []
    for i, section in enumerate(sections):
        try:
            result = next(
                model.generate(text=section.text, voice=_LOCAL_VOICE, speed=tts.speed)
            )
        except Exception as e:  # noqa: BLE001 - surface any synth failure uniformly
            raise SynthError(f"synthesis failed for {section.text!r}: {e}") from e
        path = os.path.join(out_dir, f"clip-{i:03d}.wav")
        audio_write(path, result.audio, result.sample_rate)
        duration = len(result.audio) / result.sample_rate
        clips.append(Clip(path=path, duration=duration))
    return clips
