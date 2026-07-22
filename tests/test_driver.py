import sys

import pytest

from pocumentary.driver import run_jxa, run_osascript, run_process


def test_run_osascript_pipes_script_to_stdin(monkeypatch):
    captured = {}

    def fake_run(argv, input, text, capture_output):
        captured["argv"] = argv
        captured["input"] = input

        class R:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return R()

    monkeypatch.setattr("pocumentary.driver.subprocess.run", fake_run)
    result = run_osascript("return 1")
    assert captured["argv"] == ["osascript", "-"]
    assert captured["input"] == "return 1"
    assert result.stdout == "ok"


def test_run_process_captures_stdout():
    result = run_process(["echo", "hello"])
    assert result.returncode == 0
    assert result.stdout.strip() == "hello"


def test_run_process_captures_stderr_and_returncode():
    result = run_process(["sh", "-c", "echo boom >&2; exit 3"])
    assert result.returncode == 3
    assert "boom" in result.stderr


@pytest.mark.skipif(sys.platform != "darwin", reason="JXA requires macOS")
def test_run_jxa_evaluates_javascript():
    result = run_jxa("1 + 1")
    assert result.returncode == 0
    assert result.stdout.strip() == "2"
