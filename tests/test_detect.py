from types import SimpleNamespace

import pytest

from pocumentary.detect import (
    Geometry,
    detect_geometry,
    detect_scale,
    detect_screen_device_index,
    parse_scale,
    parse_screen_size,
)


def test_parse_screen_size_typical():
    assert parse_screen_size("1512,982") == (1512, 982)


def test_parse_screen_size_tolerates_whitespace_and_float():
    assert parse_screen_size(" 1440.0 , 900.0 \n") == (1440, 900)


def test_parse_screen_size_rejects_malformed():
    with pytest.raises(ValueError, match="width,height"):
        parse_screen_size("1512 982")


def test_detect_geometry_uses_main_screen_via_jxa(monkeypatch):
    calls = {}

    def fake_run(script):
        calls["script"] = script

        class R:
            returncode = 0
            stdout = "1440,900\n"
            stderr = ""

        return R()

    monkeypatch.setattr("pocumentary.detect.sys.platform", "darwin")
    monkeypatch.setattr("pocumentary.detect.run_jxa", fake_run)
    geo = detect_geometry()
    assert geo == Geometry(width_pt=1440, height_pt=900)
    # main display, NOT the multi-monitor desktop union
    assert "mainScreen" in calls["script"]
    assert "window of desktop" not in calls["script"]


def test_detect_geometry_off_macos_raises(monkeypatch):
    monkeypatch.setattr("pocumentary.detect.sys.platform", "linux")
    with pytest.raises(RuntimeError, match="macOS"):
        detect_geometry()


def test_detect_geometry_osascript_failure(monkeypatch):
    stderr_msg = "execution error: Not authorized to send Apple events to Finder. (-1743)"

    def fake_run(script):
        class R:
            returncode = 1
            stdout = ""
            stderr = stderr_msg

        return R()

    monkeypatch.setattr("pocumentary.detect.sys.platform", "darwin")
    monkeypatch.setattr("pocumentary.detect.run_jxa", fake_run)
    with pytest.raises(RuntimeError, match="osascript failed"):
        detect_geometry()
    # Verify the underlying stderr is in the message
    try:
        detect_geometry()
    except RuntimeError as e:
        assert "Not authorized" in str(e)
        assert "-1743" in str(e)


def test_detect_scale_uses_jxa_output(monkeypatch):
    calls = {}

    def fake_run(script):
        calls["script"] = script

        class R:
            returncode = 0
            stdout = "2\n"
            stderr = ""

        return R()

    monkeypatch.setattr("pocumentary.detect.sys.platform", "darwin")
    monkeypatch.setattr("pocumentary.detect.run_jxa", fake_run)
    scale = detect_scale()
    assert scale == 2
    assert "backingScaleFactor" in calls["script"]


def test_detect_scale_off_macos_raises(monkeypatch):
    monkeypatch.setattr("pocumentary.detect.sys.platform", "linux")
    with pytest.raises(RuntimeError, match="macOS"):
        detect_scale()


def test_detect_scale_jxa_failure(monkeypatch):
    stderr_msg = "execution error: Not authorized to send Apple events. (-1743)"

    def fake_run(script):
        class R:
            returncode = 1
            stdout = ""
            stderr = stderr_msg

        return R()

    monkeypatch.setattr("pocumentary.detect.sys.platform", "darwin")
    monkeypatch.setattr("pocumentary.detect.run_jxa", fake_run)
    with pytest.raises(RuntimeError, match="osascript failed") as exc_info:
        detect_scale()
    # Verify the underlying stderr is in the message
    assert "Not authorized" in str(exc_info.value)
    assert "-1743" in str(exc_info.value)


DEVICE_LIST = """\
[AVFoundation indev @ 0x1] AVFoundation video devices:
[AVFoundation indev @ 0x1] [0] FaceTime HD Camera
[AVFoundation indev @ 0x1] [3] Capture screen 0
[AVFoundation indev @ 0x1] AVFoundation audio devices:
[AVFoundation indev @ 0x1] [0] MacBook Pro Microphone
"""


def test_parse_scale_reads_an_integer():
    assert parse_scale("2\n") == 2


def test_parse_scale_reads_a_float_form():
    """JXA may render the factor as either 2 or 2.0 depending on host."""
    assert parse_scale("2.0\n") == 2


def test_parse_scale_rejects_garbage():
    with pytest.raises(ValueError, match="backing scale factor"):
        parse_scale("")


def test_parse_scale_rejects_zero():
    with pytest.raises(ValueError, match="backing scale factor"):
        parse_scale("0")


def test_detect_screen_device_index_ignores_nonzero_returncode(monkeypatch):
    """`ffmpeg -list_devices` ALWAYS exits non-zero. Detection must still work."""
    calls = []

    def fake_run_process(args):
        calls.append(args)
        return SimpleNamespace(returncode=1, stdout="", stderr=DEVICE_LIST)

    monkeypatch.setattr("pocumentary.detect.run_process", fake_run_process)
    assert detect_screen_device_index() == 3
    assert calls[0][0] == "ffmpeg"
    assert "-list_devices" in calls[0]


def test_detect_screen_device_index_reports_missing_ffmpeg(monkeypatch):
    def fake_run_process(args):
        raise FileNotFoundError("ffmpeg")

    monkeypatch.setattr("pocumentary.detect.run_process", fake_run_process)
    with pytest.raises(RuntimeError, match="ffmpeg not found"):
        detect_screen_device_index()
