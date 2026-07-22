"""Pure gating decisions (the pure half of N10, A5).

Panes are launched in spec order, one at a time. A pane with `gate_on = "sig"`
is not launched until the previous panes have produced the file named `sig` in
the runtime directory — the file-handshake pattern from
docs/reference/fastmcp-cand003/demo_common.py (`server_ready`, `lure.txt`,
`takeover.json`) and its aws-mcp predecessor.

Both `record` (via generated AppleScript) and `dryrun` (via Python) consume the
steps this module produces, so the two paths cannot drift on *what* to wait for
even though they differ on *how* to wait.
"""
from __future__ import annotations

import os.path
from dataclasses import dataclass

from pocumentary.spec import Spec


@dataclass(frozen=True)
class PaneStep:
    """One pane's place in the launch sequence."""

    index: int  # 0-based position in spec.panes
    title: str
    wait_for: str | None  # signal to await BEFORE launching this pane
    delay: float  # seconds to pause AFTER launching it


def resolve_steps(spec: Spec) -> list[PaneStep]:
    return [
        PaneStep(index=i, title=p.title, wait_for=p.gate_on, delay=p.delay)
        for i, p in enumerate(spec.panes)
    ]


def signal_path(runtime_dir: str, signal: str) -> str:
    """Where a signal's handshake file lives. Pure string math — touches nothing."""
    return os.path.join(runtime_dir, signal)


def validate_gates(spec: Spec) -> list[str]:
    """Catch gate wiring that could only ever hang.

    Because panes launch sequentially, a pane may only gate on a signal emitted
    by a STRICTLY EARLIER pane. Anything else is an unrunnable spec, and finding
    it here costs a millisecond instead of a 60-second timeout mid-take.
    """
    errors: list[str] = []

    emitter: dict[str, int] = {}
    for i, pane in enumerate(spec.panes):
        for sig in pane.signals:
            if sig in emitter:
                errors.append(
                    f"signal {sig!r} is emitted by more than one pane "
                    f"(#{emitter[sig] + 1} and #{i + 1}); signals must be unique"
                )
                continue
            emitter[sig] = i

    for i, pane in enumerate(spec.panes):
        if pane.gate_on is None:
            continue
        where = f"[[pane]] #{i + 1} ({pane.title!r})"
        if pane.gate_on not in emitter:
            errors.append(
                f"{where}: gate_on {pane.gate_on!r} but no pane emits it; "
                f"add it to an earlier pane's `signals`"
            )
        elif emitter[pane.gate_on] >= i:
            errors.append(
                f"{where}: gate_on {pane.gate_on!r} would deadlock — it is emitted by "
                f"pane #{emitter[pane.gate_on] + 1}, which launches later"
            )

    return errors
