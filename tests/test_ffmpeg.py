import pytest

from pocumentary.ffmpeg import (
    build_ffmpeg_args,
    find_screen_device,
    parse_avfoundation_devices,
)

# Real shape of `ffmpeg -f avfoundation -list_devices true -i ""` stderr.
# Note the audio section REPEATS index 3 — the parser must stop before it.
DEVICE_LIST = """\
[AVFoundation indev @ 0x14e0450c0] AVFoundation video devices:
[AVFoundation indev @ 0x14e0450c0] [0] FaceTime HD Camera
[AVFoundation indev @ 0x14e0450c0] [1] Studio Display Camera
[AVFoundation indev @ 0x14e0450c0] [2] Desk View Camera
[AVFoundation indev @ 0x14e0450c0] [3] Capture screen 0
[AVFoundation indev @ 0x14e0450c0] AVFoundation audio devices:
[AVFoundation indev @ 0x14e0450c0] [0] MacBook Pro Microphone
[AVFoundation indev @ 0x14e0450c0] [3] Capture screen 0
"""


def test_parses_only_the_video_section():
    devices = parse_avfoundation_devices(DEVICE_LIST)
    assert devices == {
        "FaceTime HD Camera": 0,
        "Studio Display Camera": 1,
        "Desk View Camera": 2,
        "Capture screen 0": 3,
    }


def test_audio_section_cannot_shadow_a_video_index():
    """The audio list repeats index 3; if the parser ran past the audio header
    it would still map 'Capture screen 0' to 3 here by luck. Assert the audio
    device is absent to prove the boundary is respected."""
    devices = parse_avfoundation_devices(DEVICE_LIST)
    assert "MacBook Pro Microphone" not in devices


def test_finds_the_screen_capture_device():
    assert find_screen_device(parse_avfoundation_devices(DEVICE_LIST)) == 3


def test_prefers_the_lowest_numbered_screen():
    devices = {"Capture screen 1": 4, "Capture screen 0": 3, "FaceTime HD Camera": 0}
    assert find_screen_device(devices) == 3


def test_missing_screen_device_raises_lookup_error():
    with pytest.raises(LookupError, match="no 'Capture screen' device"):
        find_screen_device({"FaceTime HD Camera": 0})


def test_handles_empty_output():
    assert parse_avfoundation_devices("") == {}


def test_builds_the_reference_command():
    assert build_ffmpeg_args(3, 30, "crop=3024:1884:0:60", "/tmp/take.mov") == [
        "ffmpeg",
        "-hide_banner",
        "-f",
        "avfoundation",
        "-framerate",
        "30",
        "-i",
        "3:none",
        "-vf",
        "crop=3024:1884:0:60",
        "-pix_fmt",
        "yuv420p",
        "-y",
        "/tmp/take.mov",
    ]


def test_omits_the_filter_flag_when_not_cropping():
    args = build_ffmpeg_args(3, 30, None, "/tmp/take.mov")
    assert "-vf" not in args
    assert args[-1] == "/tmp/take.mov"


def test_honours_an_explicit_ffmpeg_path():
    args = build_ffmpeg_args(3, 30, None, "/tmp/t.mov", ffmpeg="/opt/homebrew/bin/ffmpeg")
    assert args[0] == "/opt/homebrew/bin/ffmpeg"


def test_arguments_are_a_list_never_a_shell_string():
    """A path with a space must survive as one argv element — no shell quoting."""
    args = build_ffmpeg_args(3, 30, None, "/tmp/my takes/a b.mov")
    assert args[-1] == "/tmp/my takes/a b.mov"
