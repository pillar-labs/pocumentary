"""Pure per-pane command building (N6): bake cwd + env into one shell string.

Mirrors the cdPrefix/envPrefix pattern from
docs/reference/fastmcp-cand003/record_cand003.applescript, but built in Python so
the whole command (env included) is baked once — the fix for the env-never-propagated bug.
"""
from __future__ import annotations

import shlex

from pocumentary.spec import Pane


def build_command(
    cmd: str, env: dict[str, str] | None = None, cwd: str | None = None
) -> str:
    parts = ["clear;"]
    if cwd:
        parts.append(f"cd {shlex.quote(cwd)};")
    for key, value in (env or {}).items():
        parts.append(f"{key}={shlex.quote(value)}")
    parts.append(cmd)
    return " ".join(parts)


def _fmt(value: float) -> str:
    """Render a delay without a pointless trailing '.0' (2.2 -> '2.2', 0.0 -> '0')."""
    return f"{value:g}"


def pane_env(pane: Pane, runtime_dir: str, step_delay: float) -> dict[str, str]:
    """The full environment for a pane: injected values, then the pane's own.

    DEMO_RUNTIME_DIR and DEMO_STEP_DELAY use the names the reference role
    scripts already read (docs/reference/fastmcp-cand003/demo_common.py), so an
    existing role script runs under pocumentary unmodified. The pane's own env wins,
    so an author can always override.
    """
    merged = {
        "DEMO_RUNTIME_DIR": runtime_dir,
        "DEMO_STEP_DELAY": _fmt(step_delay),
    }
    merged.update(pane.env)
    return merged
