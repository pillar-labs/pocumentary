import shutil
import subprocess

import pytest

from pocumentary.postprod import PostprodError, burn_subtitles

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")

_SRT = "1\n00:00:00,000 --> 00:00:01,000\nhello world\n"


def _make_mov(path):
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10:duration=1",
            "-pix_fmt", "yuv420p", "-y", str(path),
        ],
        check=True,
    )


def test_burn_subtitles_writes_a_captioned_file(tmp_path):
    mov = tmp_path / "in.mov"
    _make_mov(mov)
    out = tmp_path / "out.mov"
    burn_subtitles(str(mov), _SRT, str(out))
    assert out.exists() and out.stat().st_size > 0


def test_burn_subtitles_raises_on_bad_input(tmp_path):
    out = tmp_path / "out.mov"
    with pytest.raises(PostprodError):
        burn_subtitles(str(tmp_path / "nope.mov"), _SRT, str(out))


def test_burn_subtitles_reports_missing_ffmpeg(tmp_path):
    mov = tmp_path / "in.mov"
    _make_mov(mov)
    with pytest.raises(PostprodError, match="not found"):
        burn_subtitles(str(mov), _SRT, str(tmp_path / "out.mov"), ffmpeg="definitely-not-ffmpeg-xyz")


from pocumentary.postprod import mix_narration

_FFMPEG = shutil.which("ffmpeg")
_needs_ffmpeg = pytest.mark.skipif(_FFMPEG is None, reason="ffmpeg not installed")


def _mean_volume_db(mov, start, dur):
    out = subprocess.run(
        [_FFMPEG, "-hide_banner", "-ss", str(start), "-t", str(dur),
         "-i", mov, "-af", "volumedetect", "-f", "null", "/dev/null"],
        capture_output=True, text=True,
    ).stderr
    for line in out.splitlines():
        if "mean_volume:" in line:
            return float(line.split("mean_volume:")[1].strip().split()[0])
    return None


@_needs_ffmpeg
def test_mix_narration_places_clips_at_their_offsets(tmp_path):
    video = str(tmp_path / "v.mov")
    c0 = str(tmp_path / "c0.wav")
    c1 = str(tmp_path / "c1.wav")
    out = str(tmp_path / "v-narrated.mov")
    # 8s silent video; two 2s tone "clips"
    subprocess.run([_FFMPEG, "-y", "-f", "lavfi", "-i",
                    "color=c=gray:s=320x240:r=30:d=8", video], check=True,
                   capture_output=True)
    for path, freq in ((c0, 330), (c1, 440)):
        subprocess.run([_FFMPEG, "-y", "-f", "lavfi", "-i",
                        f"sine=frequency={freq}:duration=2:sample_rate=24000", path],
                       check=True, capture_output=True)

    mix_narration(video, [c0, c1], [0.0, 4.44], out, _FFMPEG)

    # output has an audio track; the second clip lands at ~4.44s
    probe = subprocess.run(
        [_FFMPEG.replace("ffmpeg", "ffprobe"), "-hide_banner", "-loglevel", "error",
         "-show_entries", "stream=codec_type", "-of", "csv", out],
        capture_output=True, text=True,
    ).stdout
    assert "audio" in probe and "video" in probe
    assert _mean_volume_db(out, 0, 1.5) > -60      # start clip present
    assert _mean_volume_db(out, 3.0, 1.0) < -80    # gap between clips is silent
    assert _mean_volume_db(out, 4.6, 1.2) > -60    # server clip present at offset


@_needs_ffmpeg
def test_mix_narration_raises_on_bad_input(tmp_path):
    with pytest.raises(PostprodError):
        mix_narration("/nonexistent.mov", ["/nonexistent.wav"], [0.0],
                      str(tmp_path / "o.mov"), _FFMPEG)


from pocumentary.postprod import _probe_duration, burn_overlays
from pocumentary.overlay import Placement

_FFPROBE = _FFMPEG.replace("ffmpeg", "ffprobe") if _FFMPEG else "ffprobe"


def _duration(path):
    out = subprocess.run(
        [_FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True,
    ).stdout
    return float(out.strip())


@_needs_ffmpeg
def test_burn_overlays_output_never_exceeds_source_even_with_looping_gif(tmp_path):
    """The runaway that once filled a disk: a looping GIF (-ignore_loop 0) with an
    overlay window reaching PAST the source must NOT produce an unbounded output.
    Output duration must stay bounded to the ~2s source, not the 999s window."""
    base = str(tmp_path / "base.mov")
    gif = str(tmp_path / "loop.gif")
    out = str(tmp_path / "out.mov")
    subprocess.run([_FFMPEG, "-y", "-f", "lavfi", "-i",
                    "color=c=black:s=160x120:r=10:d=2", "-pix_fmt", "yuv420p", base],
                   check=True, capture_output=True)
    subprocess.run([_FFMPEG, "-y", "-f", "lavfi", "-i",
                    "testsrc=s=32x32:r=5:d=1", gif], check=True, capture_output=True)

    # a MALICIOUSLY long window (starts at 1s, lasts 999s) — pre-fix this looped forever
    placements = [Placement(gif, 1.0, 999.0, 0.5, "center")]
    burn_overlays(base, [gif], placements, out, _FFMPEG, _FFPROBE)

    assert _duration(out) < 4.0        # ~2s source, NOT ~1000s


def test_probe_duration_returns_none_when_ffprobe_missing(tmp_path):
    # graceful: a missing ffprobe must not raise (per-gif -t still guards)
    assert _probe_duration(str(tmp_path / "x.mov"), "definitely-not-ffprobe-xyz") is None
