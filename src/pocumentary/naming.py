"""Pure output-artifact naming and prune selection (A8 / R8.1).

The reference wrapper built its filename with `STAMP="$(date +%Y%m%d-%H%M%S)"`;
the same format is used here because it sorts chronologically as plain text,
which is what makes prune selection a pure sort-and-slice.
"""
from __future__ import annotations

STAMP_FORMAT = "%Y%m%d-%H%M%S"
_PLACEHOLDER = "{stamp}"


def expand_out(template: str, stamp: str) -> str:
    """Fill the `{stamp}` placeholder in an output template."""
    return template.replace(_PLACEHOLDER, stamp)


def out_glob(template: str) -> str:
    """The glob that matches every take produced from this template."""
    return template.replace(_PLACEHOLDER, "*")


def select_prunable(paths: list[str], keep: int) -> list[str]:
    """Which existing takes to delete so that at most `keep` remain.

    `keep <= 0` means keep everything — deletion is strictly opt-in, so a
    misconfigured spec can never silently destroy recordings.
    """
    if keep <= 0:
        return []
    ordered = sorted(paths)
    if len(ordered) <= keep:
        return []
    return ordered[: len(ordered) - keep]
