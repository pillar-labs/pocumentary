"""Headless demo execution (N13 local, A2.2) — the cheap iteration loop, R5.

Runs the same panes as `record` but as plain subprocesses: no Terminal, no
AppleScript, no ffmpeg, no pacing. That makes it fast, non-disruptive, and
runnable anywhere — including CI, which is the point. Do NOT add a macOS guard
to this module.

Each pane's combined stdout+stderr is redirected to a per-pane file in the
runtime directory rather than to a pipe. A pipe blocks the writer once ~64KB
goes unread, so a chatty pane that must also emit a gate signal would hang
before signalling — starving the gate and forcing a false timeout. A file
never blocks the writer, so the pane always makes progress; the consumer reads
the captured output back at its leisure.

Environment is *added to* the ambient one rather than replacing it, because
role scripts need PATH, HOME, and a working Python.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import time
from dataclasses import dataclass

from pocumentary.cmd import pane_env
from pocumentary.gates import resolve_steps, signal_path
from pocumentary.spec import Pane, Spec
from pocumentary.verify import wait_for_expectations


@dataclass(frozen=True)
class LaunchedPane:
    """A running headless pane and the file capturing its combined output."""

    title: str
    proc: subprocess.Popen
    log_path: str

    def read_output(self) -> str:
        """Everything the pane has written so far. Never raises."""
        try:
            with open(self.log_path, encoding="utf-8", errors="replace") as f:
                return f.read()
        except FileNotFoundError:
            return ""


def launch_pane(pane: Pane, runtime_dir: str, step_delay: float = 0.0) -> LaunchedPane:
    """Start one pane's command headlessly, capturing its output to a file.

    The command is handed to `sh -c` verbatim rather than through
    cmd.build_command: that builder prefixes `clear;` for on-screen legibility,
    which only emits escape noise when there is no terminal. Env and cwd are
    passed to the process directly instead of being baked into the string.
    stdout and stderr are merged into one per-pane file under runtime_dir so a
    verbose pane can never deadlock against an undrained pipe.
    """
    env = dict(os.environ)
    env.update(pane_env(pane, runtime_dir, step_delay))
    fd, log_path = tempfile.mkstemp(dir=runtime_dir, prefix="pane-", suffix=".log")
    log_file = os.fdopen(fd, "w")
    try:
        proc = subprocess.Popen(
            ["/bin/sh", "-c", pane.cmd],
            env=env,
            cwd=pane.cwd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
    finally:
        log_file.close()  # the child holds its own dup; the parent's copy is done
    return LaunchedPane(title=pane.title, proc=proc, log_path=log_path)


def terminate_all(panes: list[LaunchedPane], grace: float = 5.0) -> None:
    """Stop every still-running pane, escalating to kill if it will not go."""
    alive = [p for p in panes if p.proc.poll() is None]
    for p in alive:
        p.proc.terminate()
    for p in alive:
        try:
            p.proc.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            p.proc.kill()
            p.proc.wait(timeout=grace)


@dataclass(frozen=True)
class HeadlessResult:
    """The verdict of one headless run."""

    missing: list[str]  # verify expectations never met
    gate_timeout: str | None  # the signal that never arrived, if any
    pane_output: dict[str, str]  # pane title -> combined stdout/stderr

    @property
    def ok(self) -> bool:
        return not self.missing and self.gate_timeout is None


def wait_for_signal(
    runtime_dir: str, signal: str, timeout: float, poll: float = 0.05
) -> bool:
    """Block until a handshake file appears. False means it never did."""
    path = signal_path(runtime_dir, signal)
    deadline = time.monotonic() + timeout
    while True:
        if os.path.exists(path):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(poll)


def run_headless(spec: Spec, runtime_dir: str) -> HeadlessResult:
    """Run every pane headlessly in gated order and return the verdict.

    Panes are always cleaned up, including when a gate times out — a demo whose
    server runs forever must not outlive the dryrun that started it. Each pane's
    output is read back from its capture file after the processes are stopped.
    """
    os.makedirs(runtime_dir, exist_ok=True)

    launched: list[LaunchedPane] = []
    gate_timeout: str | None = None

    try:
        for step in resolve_steps(spec):
            if step.wait_for and not wait_for_signal(
                runtime_dir, step.wait_for, spec.recording.gate_timeout
            ):
                gate_timeout = step.wait_for
                break
            launched.append(launch_pane(spec.panes[step.index], runtime_dir))

        if gate_timeout:
            missing = []
        elif spec.verify.expect:
            missing = wait_for_expectations(runtime_dir, spec.verify)
        else:
            # No success predicate to wait on, so nothing signals that the demo
            # is done. Give the panes time to finish their work and produce
            # diagnostic output — tearing down immediately would race the
            # just-forked processes and capture nothing. Bounded by
            # verify.timeout so a pane that never exits (a server) can't hang
            # the dryrun; cleanup in the finally block then stops it.
            _wait_for_exit(launched, spec.verify.timeout)
            missing = []
    finally:
        terminate_all(launched)
        output = {lp.title: lp.read_output() for lp in launched}

    return HeadlessResult(missing=missing, gate_timeout=gate_timeout, pane_output=output)


def _wait_for_exit(panes: list[LaunchedPane], timeout: float) -> None:
    """Give the launched panes up to `timeout` seconds in total to exit on
    their own before the caller tears them down."""
    deadline = time.monotonic() + timeout
    for p in panes:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            p.proc.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            break
