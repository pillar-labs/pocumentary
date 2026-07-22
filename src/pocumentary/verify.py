"""Effectful success verification (N11, R6).

The demo's own role scripts assert their outcome by writing handshake files —
`takeover.json` in docs/reference/fastmcp-cand003. pocumentary's job is only to
notice whether they appeared, and to make a missing one a non-zero exit rather
than a recording nobody watches closely enough to spot the failure in.
"""
from __future__ import annotations

import os
import time

from pocumentary.gates import signal_path
from pocumentary.spec import Verify


def check_expectations(runtime_dir: str, v: Verify) -> list[str]:
    """Which expected signals are absent right now, in spec order."""
    return [name for name in v.expect if not os.path.exists(signal_path(runtime_dir, name))]


def wait_for_expectations(runtime_dir: str, v: Verify, poll: float = 0.1) -> list[str]:
    """Poll until every expectation is met or the timeout elapses.

    Returns whatever is still missing — an empty list means the demo passed.
    """
    if not v.expect:
        return []
    deadline = time.monotonic() + v.timeout
    while True:
        missing = check_expectations(runtime_dir, v)
        if not missing or time.monotonic() >= deadline:
            return missing
        time.sleep(poll)
