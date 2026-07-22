import os
import sys
import threading
import time
from pathlib import Path

import pytest

from pocumentary.record import RecordError, prune_takes, start_recording, stop_recording

SLEEPER = [sys.executable, "-c", "import time; time.sleep(30)"]


def test_start_recording_launches_the_process(tmp_path):
    log = tmp_path / "ff.log"
    proc = start_recording(SLEEPER, str(log))
    try:
        assert proc.poll() is None  # still running
        assert log.exists()
    finally:
        stop_recording(proc, timeout=5)


def test_stop_recording_terminates_a_live_process(tmp_path):
    proc = start_recording(SLEEPER, str(tmp_path / "ff.log"))
    stop_recording(proc, timeout=5)
    assert proc.poll() is not None


def test_stop_recording_is_safe_on_an_already_dead_process(tmp_path):
    proc = start_recording([sys.executable, "-c", ""], str(tmp_path / "ff.log"))
    time.sleep(0.5)
    assert stop_recording(proc, timeout=5) == 0


def test_stop_recording_kills_a_process_that_ignores_sigint(tmp_path):
    """ffmpeg normally flushes and exits on SIGINT. If it hangs we must not."""
    stubborn = [
        sys.executable,
        "-c",
        "import signal, time; signal.signal(signal.SIGINT, signal.SIG_IGN); time.sleep(30)",
    ]
    proc = start_recording(stubborn, str(tmp_path / "ff.log"))
    stop_recording(proc, timeout=1)
    assert proc.poll() is not None


def test_start_recording_reports_a_missing_executable(tmp_path):
    with pytest.raises(RecordError, match="not found"):
        start_recording(["definitely-not-a-real-binary-xyz"], str(tmp_path / "ff.log"))


def test_start_recording_reports_a_bad_log_path(tmp_path):
    """A caller catching RecordError must not be blindsided by a raw OSError
    from opening the log file — the contract covers every start failure."""
    bad_log = "/nonexistent-dir-xyz/ff.log"
    with pytest.raises(RecordError, match=bad_log):
        start_recording(SLEEPER, bad_log)


def test_ffmpeg_stderr_lands_in_the_log(tmp_path):
    log = tmp_path / "ff.log"
    proc = start_recording(
        [sys.executable, "-c", "import sys; sys.stderr.write('boom\\n')"], str(log)
    )
    # Give the child a moment to actually run and flush before we signal it —
    # without this, SIGINT can race the interpreter's own startup and kill it
    # before "boom" is ever written (observed deterministically on this host).
    time.sleep(0.2)
    stop_recording(proc, timeout=5)
    assert "boom" in log.read_text()


def test_prune_takes_deletes_the_oldest(tmp_path):
    for stamp in ("20260721-090000", "20260721-143000", "20260722-010000"):
        (tmp_path / f"rec-{stamp}.mov").write_text("x")
    deleted = prune_takes(str(tmp_path), "rec-{stamp}.mov", keep=1)
    assert [Path(p).name for p in deleted] == [
        "rec-20260721-090000.mov",
        "rec-20260721-143000.mov",
    ]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["rec-20260722-010000.mov"]


def test_prune_takes_keeps_everything_by_default(tmp_path):
    (tmp_path / "rec-20260721-090000.mov").write_text("x")
    assert prune_takes(str(tmp_path), "rec-{stamp}.mov", keep=0) == []
    assert len(list(tmp_path.iterdir())) == 1


def test_prune_takes_ignores_unrelated_files(tmp_path):
    """Only files matching this spec's own out-template are ever candidates."""
    (tmp_path / "rec-20260721-090000.mov").write_text("x")
    (tmp_path / "rec-20260722-010000.mov").write_text("x")
    (tmp_path / "important.mov").write_text("x")
    (tmp_path / "notes.txt").write_text("x")
    prune_takes(str(tmp_path), "rec-{stamp}.mov", keep=1)
    names = sorted(p.name for p in tmp_path.iterdir())
    assert names == ["important.mov", "notes.txt", "rec-20260722-010000.mov"]


def test_prune_takes_continues_past_a_failed_removal(tmp_path, monkeypatch):
    """One doomed file's removal failing must not abort the rest of the prune,
    and only the files actually deleted are reported back."""
    stamps = ("20260721-090000", "20260721-143000", "20260722-010000")
    for stamp in stamps:
        (tmp_path / f"rec-{stamp}.mov").write_text("x")
    doomed_but_unremovable = str(tmp_path / "rec-20260721-090000.mov")

    real_remove = os.remove

    def flaky_remove(path):
        if path == doomed_but_unremovable:
            raise PermissionError("simulated permission failure")
        real_remove(path)

    monkeypatch.setattr(os, "remove", flaky_remove)

    deleted = prune_takes(str(tmp_path), "rec-{stamp}.mov", keep=1)

    assert deleted == [str(tmp_path / "rec-20260721-143000.mov")]
    remaining = sorted(p.name for p in tmp_path.iterdir())
    assert remaining == ["rec-20260721-090000.mov", "rec-20260722-010000.mov"]


def test_prune_takes_treats_an_already_vanished_file_as_benign(tmp_path, monkeypatch):
    """A file that disappeared out from under us (a benign race) is skipped,
    not treated as an error — the desired end state was already achieved."""
    stamps = ("20260721-090000", "20260721-143000", "20260722-010000")
    for stamp in stamps:
        (tmp_path / f"rec-{stamp}.mov").write_text("x")
    vanished = str(tmp_path / "rec-20260721-090000.mov")
    os.remove(vanished)  # simulate the race: it's already gone before we try

    real_remove = os.remove

    def vanishing_remove(path):
        if path == vanished:
            raise FileNotFoundError(f"already gone: {path}")
        real_remove(path)

    monkeypatch.setattr(os, "remove", vanishing_remove)

    deleted = prune_takes(str(tmp_path), "rec-{stamp}.mov", keep=1)

    assert deleted == [str(tmp_path / "rec-20260721-143000.mov")]
    remaining = sorted(p.name for p in tmp_path.iterdir())
    assert remaining == ["rec-20260722-010000.mov"]


from types import SimpleNamespace

from pocumentary.detect import Geometry
from pocumentary.gen import BACKDROP_TITLE
from pocumentary.record import run_take
from pocumentary.spec import Layout, Pane, Recording, Spec


def _spec():
    return Spec(
        recording=Recording(fps=30, hold=0.0),
        layout=Layout(mode="columns"),
        panes=(Pane(title="A", cmd="echo a"),),
    )


class _FakeRecorder:
    """Records the call order so we can assert the take's sequencing."""

    def __init__(self):
        self.events = []

    def start(self, args, log_path):
        self.events.append(("start", args))
        return SimpleNamespace(poll=lambda: None, returncode=0)

    def stop(self, proc, timeout=15.0):
        self.events.append(("stop",))
        return 0


def test_run_take_sequences_cleanup_backdrop_record_and_cleanup(tmp_path, monkeypatch):
    recorder = _FakeRecorder()
    scripts = []

    monkeypatch.setattr("pocumentary.record.start_recording", recorder.start)
    monkeypatch.setattr("pocumentary.record.stop_recording", recorder.stop)

    def fake_osascript(script):
        scripts.append(script)
        recorder.events.append(("osascript",))
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr("pocumentary.record.run_osascript", fake_osascript)

    run_take(
        _spec(),
        Geometry(width_pt=1512, height_pt=982),
        scale=2,
        device_index=3,
        out_path=str(tmp_path / "t.mov"),
        log_path=str(tmp_path / "t.log"),
        runtime_dir=str(tmp_path / "rt"),
    )

    assert [e[0] for e in recorder.events] == [
        "osascript",  # pre-take cleanup, before the camera rolls
        "osascript",  # backdrop opened, still before the camera rolls
        "start",
        "osascript",  # the take itself
        "stop",
        "osascript",  # post-take cleanup, after the camera stops
    ]
    assert "closeDemoWindows" in scripts[0]
    assert BACKDROP_TITLE in scripts[0]  # a leftover backdrop from a crashed run is cleared too
    assert "openWindow" in scripts[1]
    assert BACKDROP_TITLE in scripts[1]  # the backdrop script itself
    assert "openWindow" in scripts[2]
    assert "closeDemoWindows" in scripts[3]
    assert BACKDROP_TITLE in scripts[3]  # backdrop is closed alongside the panes


def test_run_take_opens_the_backdrop_before_ffmpeg_starts(tmp_path, monkeypatch):
    """The backdrop must be up before start_recording is called, so even the
    settle period before the first pane opens records a clean region."""
    recorder = _FakeRecorder()
    scripts = []

    monkeypatch.setattr("pocumentary.record.start_recording", recorder.start)
    monkeypatch.setattr("pocumentary.record.stop_recording", recorder.stop)

    def fake_osascript(script):
        scripts.append(script)
        recorder.events.append(("osascript",))
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr("pocumentary.record.run_osascript", fake_osascript)

    run_take(
        _spec(),
        Geometry(width_pt=1512, height_pt=982),
        scale=2,
        device_index=3,
        out_path=str(tmp_path / "t.mov"),
        log_path=str(tmp_path / "t.log"),
        runtime_dir=str(tmp_path / "rt"),
    )

    backdrop_script_index = next(
        i for i, s in enumerate(scripts) if "openWindow" in s and BACKDROP_TITLE in s
    )
    start_event_index = next(i for i, e in enumerate(recorder.events) if e[0] == "start")
    # translate the backdrop's position among osascript calls into its position
    # in the overall event list, so the comparison is against "start" directly
    osascript_event_indices = [i for i, e in enumerate(recorder.events) if e[0] == "osascript"]
    backdrop_event_index = osascript_event_indices[backdrop_script_index]
    assert backdrop_event_index < start_event_index

    post_cleanup_script = scripts[-1]
    assert "closeDemoWindows" in post_cleanup_script
    assert BACKDROP_TITLE in post_cleanup_script


def test_run_take_passes_the_computed_crop_to_ffmpeg(tmp_path, monkeypatch):
    recorder = _FakeRecorder()
    monkeypatch.setattr("pocumentary.record.start_recording", recorder.start)
    monkeypatch.setattr("pocumentary.record.stop_recording", recorder.stop)
    monkeypatch.setattr(
        "pocumentary.record.run_osascript",
        lambda s: SimpleNamespace(returncode=0, stdout="ok", stderr=""),
    )

    run_take(
        _spec(),
        Geometry(width_pt=1512, height_pt=982),
        scale=2,
        device_index=3,
        out_path=str(tmp_path / "t.mov"),
        log_path=str(tmp_path / "t.log"),
        runtime_dir=str(tmp_path / "rt"),
    )

    args = next(e[1] for e in recorder.events if e[0] == "start")
    assert "-vf" in args
    # one pane, full width: union is the whole tiled region
    assert args[args.index("-vf") + 1].startswith("crop=")
    assert "3:none" in args


def test_run_take_stops_the_recorder_even_if_the_take_fails(tmp_path, monkeypatch):
    """A failing osascript must not leave ffmpeg running and the .mov unfinalised."""
    recorder = _FakeRecorder()
    monkeypatch.setattr("pocumentary.record.start_recording", recorder.start)
    monkeypatch.setattr("pocumentary.record.stop_recording", recorder.stop)

    calls = {"n": 0}

    def flaky(script):
        calls["n"] += 1
        recorder.events.append(("osascript",))
        if calls["n"] == 3:  # the take script (1: pre-take cleanup, 2: backdrop)
            return SimpleNamespace(returncode=1, stdout="", stderr="-1743 not authorised")
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr("pocumentary.record.run_osascript", flaky)

    with pytest.raises(RecordError, match="1743"):
        run_take(
            _spec(),
            Geometry(width_pt=1512, height_pt=982),
            scale=2,
            device_index=3,
            out_path=str(tmp_path / "t.mov"),
            log_path=str(tmp_path / "t.log"),
            runtime_dir=str(tmp_path / "rt"),
        )

    assert ("stop",) in recorder.events


def test_run_take_runs_post_cleanup_and_reraises_when_the_take_script_fails(
    tmp_path, monkeypatch
):
    """A failing take script must not skip cleanup — every pane window and
    the full-screen backdrop must still be closed — but the original error
    must still propagate: cleanup is best-effort, not error-swallowing for
    an in-flight failure."""
    recorder = _FakeRecorder()
    monkeypatch.setattr("pocumentary.record.start_recording", recorder.start)
    monkeypatch.setattr("pocumentary.record.stop_recording", recorder.stop)

    calls = {"n": 0}

    def flaky(script):
        calls["n"] += 1
        recorder.events.append(("osascript",))
        if calls["n"] == 3:  # the take script (1: pre-take cleanup, 2: backdrop)
            return SimpleNamespace(returncode=1, stdout="", stderr="-1743 not authorised")
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr("pocumentary.record.run_osascript", flaky)

    with pytest.raises(RecordError, match="1743"):
        run_take(
            _spec(),
            Geometry(width_pt=1512, height_pt=982),
            scale=2,
            device_index=3,
            out_path=str(tmp_path / "t.mov"),
            log_path=str(tmp_path / "t.log"),
            runtime_dir=str(tmp_path / "rt"),
        )

    assert [e[0] for e in recorder.events] == [
        "osascript",  # pre-take cleanup
        "osascript",  # backdrop
        "start",
        "osascript",  # the take itself (fails)
        "stop",
        "osascript",  # post-take cleanup still runs despite the failure above
    ]


def test_run_take_runs_cleanup_when_the_backdrop_script_fails(tmp_path, monkeypatch):
    """The backdrop script can fail partway through, after it has already
    created its full-screen window. Cleanup must still run to close it, and
    ffmpeg must never be started since the take never actually rolled."""
    recorder = _FakeRecorder()
    monkeypatch.setattr("pocumentary.record.start_recording", recorder.start)
    monkeypatch.setattr("pocumentary.record.stop_recording", recorder.stop)

    calls = {"n": 0}

    def flaky(script):
        calls["n"] += 1
        recorder.events.append(("osascript",))
        if calls["n"] == 2:  # the backdrop script (1: pre-take cleanup)
            return SimpleNamespace(returncode=1, stdout="", stderr="backdrop boom")
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr("pocumentary.record.run_osascript", flaky)

    with pytest.raises(RecordError, match="backdrop boom"):
        run_take(
            _spec(),
            Geometry(width_pt=1512, height_pt=982),
            scale=2,
            device_index=3,
            out_path=str(tmp_path / "t.mov"),
            log_path=str(tmp_path / "t.log"),
            runtime_dir=str(tmp_path / "rt"),
        )

    assert [e[0] for e in recorder.events] == [
        "osascript",  # pre-take cleanup
        "osascript",  # backdrop (fails, but may have already opened its window)
        "osascript",  # cleanup still runs even though the backdrop failed
    ]


def test_run_take_does_not_raise_when_post_take_cleanup_fails(tmp_path, monkeypatch):
    """Post-take cleanup is best-effort: once the take itself has succeeded,
    a cleanup script returning non-zero must never turn that good take into
    a reported failure (mirrors the deliberate contract on prune_takes)."""
    recorder = _FakeRecorder()
    monkeypatch.setattr("pocumentary.record.start_recording", recorder.start)
    monkeypatch.setattr("pocumentary.record.stop_recording", recorder.stop)

    calls = {"n": 0}

    def flaky(script):
        calls["n"] += 1
        recorder.events.append(("osascript",))
        if calls["n"] == 4:  # post-take cleanup (1: pre, 2: backdrop, 3: take)
            return SimpleNamespace(returncode=1, stdout="", stderr="cleanup boom")
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr("pocumentary.record.run_osascript", flaky)

    run_take(  # must not raise despite the post-take cleanup failure
        _spec(),
        Geometry(width_pt=1512, height_pt=982),
        scale=2,
        device_index=3,
        out_path=str(tmp_path / "t.mov"),
        log_path=str(tmp_path / "t.log"),
        runtime_dir=str(tmp_path / "rt"),
    )

    assert [e[0] for e in recorder.events] == [
        "osascript",  # pre-take cleanup
        "osascript",  # backdrop
        "start",
        "osascript",  # the take itself
        "stop",
        "osascript",  # post-take cleanup (fails, but swallowed)
    ]


def test_run_take_creates_the_runtime_dir(tmp_path, monkeypatch):
    recorder = _FakeRecorder()
    monkeypatch.setattr("pocumentary.record.start_recording", recorder.start)
    monkeypatch.setattr("pocumentary.record.stop_recording", recorder.stop)
    monkeypatch.setattr(
        "pocumentary.record.run_osascript",
        lambda s: SimpleNamespace(returncode=0, stdout="ok", stderr=""),
    )
    runtime = tmp_path / "rt"

    run_take(
        _spec(),
        Geometry(width_pt=1512, height_pt=982),
        scale=2,
        device_index=3,
        out_path=str(tmp_path / "t.mov"),
        log_path=str(tmp_path / "t.log"),
        runtime_dir=str(runtime),
    )

    assert runtime.is_dir()


def test_poll_timeline_records_first_appearance_offsets(tmp_path):
    from pocumentary.record import _poll_timeline

    a = tmp_path / "a"
    b = tmp_path / "b"
    watches = {"eventA": str(a), "eventB": str(b)}
    stop = threading.Event()
    offsets: dict[str, float] = {}
    t0 = time.monotonic()

    th = threading.Thread(target=_poll_timeline, args=(watches, t0, stop, offsets))
    th.start()
    a.write_text("")          # eventA fires almost immediately
    time.sleep(0.25)
    b.write_text("")          # eventB fires clearly later
    time.sleep(0.15)
    stop.set()
    th.join(timeout=2)

    assert set(offsets) == {"eventA", "eventB"}
    assert offsets["eventB"] > offsets["eventA"] >= 0


def test_poll_timeline_final_sweep_catches_a_late_event(tmp_path):
    """An event that fires between the last poll and `stop` is still caught by
    the final sweep after the loop exits."""
    from pocumentary.record import _poll_timeline

    a = tmp_path / "a"
    watches = {"eventA": str(a)}
    stop = threading.Event()
    offsets: dict[str, float] = {}

    a.write_text("")          # already present
    stop.set()                # stop BEFORE the thread's first loop check
    _poll_timeline(watches, time.monotonic(), stop, offsets)  # runs inline
    assert "eventA" in offsets


def test_write_timeline_includes_start_and_events(tmp_path):
    from pocumentary.record import _write_timeline
    from pocumentary.subtitles import load_timeline

    path = tmp_path / "out.mov.timeline.json"
    _write_timeline(str(path), {"server_ready": 3.5, "pane:1  S": 2.0})
    tl = load_timeline(path.read_text())
    assert tl == {"start": 0.0, "pane:1  S": 2.0, "server_ready": 3.5}


def test_write_timeline_is_best_effort_on_bad_path(tmp_path):
    """A write problem must never raise — a take has already succeeded by then."""
    from pocumentary.record import _write_timeline

    _write_timeline("/nonexistent-dir-xyz/out.timeline.json", {"sig": 1.0})  # no raise
