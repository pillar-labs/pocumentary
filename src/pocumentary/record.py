"""Effectful recorder edge (N9) and take pruning (N12/R8.1).

ffmpeg runs as a Python child process rather than from inside AppleScript (as
docs/reference/fastmcp-cand003/record_cand003.applescript did), so its exit
status and stderr reach the CLI's exit code instead of vanishing into a log.

Stopping mirrors the reference's `kill -INT` then hard-kill fallback: SIGINT
lets ffmpeg finalise the container, which a SIGKILL would leave unplayable.
"""
from __future__ import annotations

import glob
import os
import signal
import subprocess
import threading
import time

from pocumentary.crop import resolve_crop
from pocumentary.detect import Geometry
from pocumentary.driver import run_osascript
from pocumentary.ffmpeg import build_ffmpeg_args
from pocumentary.gen import (
    BACKDROP_TITLE,
    generate_backdrop_applescript,
    generate_cleanup_applescript,
    generate_record_applescript,
)
from pocumentary.layout import solve_layout
from pocumentary.naming import out_glob, select_prunable
from pocumentary.spec import Spec
from pocumentary.subtitles import build_timeline_json, timeline_watches

POLLER_POLL_S = 0.05  # matches dryrun.wait_for_signal; sub-second event spacing
POLLER_JOIN_TIMEOUT_S = 2.0


class RecordError(Exception):
    """Raised when the recorder cannot be started or stopped cleanly."""


def start_recording(args: list[str], log_path: str) -> subprocess.Popen:
    """Launch the capture process, sending all its output to `log_path`."""
    # Not a `with` block: the fd must stay open across the Popen call below (so
    # the child can dup it) and is closed explicitly in the `finally` there,
    # after the child has its own copy.
    try:
        log = open(log_path, "w")  # noqa: SIM115
    except OSError as e:
        raise RecordError(f"could not open recorder log at {log_path!r}: {e}") from e
    try:
        return subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT, text=True)
    except FileNotFoundError as e:
        raise RecordError(
            f"recorder not found: {args[0]!r}. Install ffmpeg (brew install ffmpeg)."
        ) from e
    except OSError as e:
        raise RecordError(f"could not start recorder: {e}") from e
    finally:
        log.close()


def stop_recording(proc: subprocess.Popen, timeout: float = 15.0) -> int:
    """SIGINT the recorder and wait for it to finalise; hard-kill if it hangs.

    Returns the recorder's raw exit status — do NOT treat a non-zero return
    as failure. Against real ffmpeg (7.1.1), a *successful* SIGINT stop exits
    with status **255**; that is the expected, healthy outcome of this
    function's normal path, not an error. On POSIX, a process killed by an
    uncaught signal (e.g. the hard-kill fallback below) instead yields a
    *negative* return code (`-signal number`). Callers that need to know
    whether the take actually succeeded must inspect the output file / log,
    not this return value.
    """
    if proc.poll() is not None:
        return proc.returncode

    proc.send_signal(signal.SIGINT)
    try:
        return proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        return proc.wait(timeout=5)


def _sweep_once(remaining: dict[str, str], t0: float, offsets: dict[str, float]) -> None:
    """Move any watched files that now exist into `offsets`, timed from t0."""
    for event, path in list(remaining.items()):
        if os.path.exists(path):
            offsets[event] = time.monotonic() - t0
            del remaining[event]


def _poll_timeline(
    watches: dict[str, str],
    t0: float,
    stop: threading.Event,
    offsets: dict[str, float],
    poll: float = POLLER_POLL_S,
) -> None:
    """Record each watched event's first-appearance offset from t0.

    Runs on a background thread while the (blocking) take script drives the
    screen. Times events with time.monotonic() — never AppleScript's clock (BSD
    `date` has no sub-second precision; see docs/spike-v6-subtitle-timeline.md).
    A final sweep after `stop` catches an event that fired between the last poll
    and the take returning.
    """
    remaining = dict(watches)
    while remaining and not stop.is_set():
        _sweep_once(remaining, t0, offsets)
        if remaining:
            time.sleep(poll)
    _sweep_once(remaining, t0, offsets)


def _write_timeline(path: str, offsets: dict[str, float]) -> None:
    """Write the timeline sidecar. Best-effort: a take has already succeeded by
    the time this runs, so a write problem must not turn it into an error (the
    same deliberate contract as prune_takes / post-take cleanup)."""
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(build_timeline_json(offsets))
    except OSError:
        pass


def prune_takes(directory: str, template: str, keep: int) -> list[str]:
    """Delete old takes matching this spec's own out-template. Opt-in only.

    Files are matched by the template's glob, so a take from a different spec
    (or any unrelated file) in the same directory is never touched.

    Pruning is best-effort housekeeping and never fails a take: it is called
    after a recording has already succeeded, so a pruning problem must never
    turn a good take into an error. This function therefore never raises.
    A file that has already vanished (`FileNotFoundError`) is treated as a
    benign race — the desired end state (the file is gone) is already
    achieved, so it is silently skipped. Any other `OSError` on one file
    (e.g. a permissions problem) is likewise skipped rather than aborting the
    rest of the prune. The return value lists only the paths that were
    *actually* deleted, so callers can trust it rather than assuming every
    candidate was removed.
    """
    candidates = glob.glob(os.path.join(directory, out_glob(template)))
    doomed = select_prunable(candidates, keep)
    deleted = []
    for path in doomed:
        try:
            os.remove(path)
        except OSError:
            # Covers both a benign already-gone race (FileNotFoundError, a
            # subclass of OSError) and any other per-file failure (e.g.
            # PermissionError). Either way: skip this file and keep going —
            # see docstring, this is a deliberate best-effort contract.
            continue
        deleted.append(path)
    return deleted


def run_take(
    spec: Spec,
    geometry: Geometry,
    scale: int,
    device_index: int,
    out_path: str,
    log_path: str,
    runtime_dir: str,
    ffmpeg: str = "ffmpeg",
) -> None:
    """Run one on-screen take: clear the stage, roll, act, cut, tidy up.

    Cleanup brackets the recording so leftover windows never appear on camera
    and the tidy-up is not filmed either. A full-screen backdrop window is
    opened before ffmpeg starts, so the only thing ever behind or between the
    staggered panes — including during the settle period before the first
    pane appears — is a blank window, never the operator's own desktop.

    Post-take cleanup runs on every exit path once the backdrop has been
    requested — including a backdrop script that fails partway through
    (which may have already created its window before failing) and a take
    script that fails outright — so a stranded pane or a stranded full-screen
    backdrop is never left on the operator's screen. That final cleanup is
    itself best-effort: mirroring the deliberate contract documented on
    `prune_takes`, a cleanup failure must never turn a successful take into
    an error, and must never mask an in-flight take exception, so it is
    swallowed rather than raised.
    """
    os.makedirs(runtime_dir, exist_ok=True)

    bounds = solve_layout(
        geometry.width_pt, geometry.height_pt, spec.layout.mode, len(spec.panes)
    )
    crop_filter = resolve_crop(spec.recording.crop, bounds, scale)
    titles = [p.title for p in spec.panes]
    cleanup_titles = [*titles, BACKDROP_TITLE]

    _run_script(generate_cleanup_applescript(cleanup_titles), "pre-take cleanup")
    try:
        _run_script(
            generate_backdrop_applescript(geometry.width_pt, geometry.height_pt), "backdrop"
        )

        args = build_ffmpeg_args(
            device_index, spec.recording.fps, crop_filter, out_path, ffmpeg
        )
        proc = start_recording(args, log_path)
        t0 = time.monotonic()
        stop = threading.Event()
        offsets: dict[str, float] = {}
        poller = threading.Thread(
            target=_poll_timeline,
            args=(timeline_watches(spec, runtime_dir), t0, stop, offsets),
            daemon=True,
        )
        poller.start()
        try:
            _run_script(generate_record_applescript(spec, bounds, runtime_dir), "take")
        finally:
            stop.set()
            poller.join(timeout=POLLER_JOIN_TIMEOUT_S)
            stop_recording(proc)
            _write_timeline(f"{out_path}.timeline.json", offsets)
    finally:
        _cleanup_best_effort(cleanup_titles)


def _cleanup_best_effort(cleanup_titles: list[str]) -> None:
    """Close every pane window and the backdrop, swallowing any failure.

    Called from `run_take`'s outer `finally`, so it always runs after the
    backdrop has been requested — after a successful take, a failed take
    script, or a backdrop script that failed partway through (and so may
    have already opened its window). By the time this runs, either the take
    already succeeded (a cleanup problem must not turn a good take into an
    error) or an exception is already propagating (a cleanup problem must
    not mask it). Either way, this function never raises — the same
    deliberate best-effort contract documented on `prune_takes`.
    """
    try:
        _run_script(generate_cleanup_applescript(cleanup_titles), "post-take cleanup")
    except RecordError:
        pass


def _run_script(script: str, what: str) -> None:
    result = run_osascript(script)
    if result.returncode != 0:
        raise RecordError(f"{what} failed: {result.stderr.strip()}")
