"""Effectful external-process runners (N8).

Every subprocess pocumentary launches goes through here, so the pure core stays
free of I/O and tests have exactly one seam to fake.
"""
from __future__ import annotations

import subprocess


def run_osascript(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(["osascript", "-"], input=script, text=True, capture_output=True)


def run_jxa(script: str) -> subprocess.CompletedProcess:
    """Run JavaScript for Automation — the only route to AppKit values like
    NSScreen's backingScaleFactor, which AppleScript cannot reach."""
    return subprocess.run(
        ["osascript", "-l", "JavaScript", "-"],
        input=script,
        text=True,
        capture_output=True,
    )


def run_process(args: list[str]) -> subprocess.CompletedProcess:
    """Run an external command with no shell. Raises FileNotFoundError if the
    executable is missing — callers turn that into an actionable message."""
    return subprocess.run(args, text=True, capture_output=True)
