"""Pure layout solver (N4): screen points + mode + pane count -> window bounds.

Column bounds reproduce the hand-tuned values from
docs/reference/fastmcp-cand003/record_cand003.applescript (top=30, bottom=height-10,
full-width columns).
"""
from __future__ import annotations

import math

Bounds = tuple[int, int, int, int]  # (x1, y1, x2, y2) in screen points

MENU_BAR_PT = 30  # leave the macOS menu bar uncovered
BOTTOM_MARGIN_PT = 10  # small gap above the Dock / screen edge


def _grid_shape(mode: str, n: int) -> tuple[int, int]:
    if mode == "columns":
        return n, 1  # (cols, rows)
    if mode == "rows":
        return 1, n
    if mode == "grid":
        cols = math.ceil(math.sqrt(n))
        rows = math.ceil(n / cols)
        return cols, rows
    raise ValueError(f"unknown layout mode: {mode!r}")


def solve_layout(width_pt: int, height_pt: int, mode: str, n: int) -> list[Bounds]:
    if n < 1:
        raise ValueError("layout needs at least one pane")

    cols, rows = _grid_shape(mode, n)
    top = MENU_BAR_PT
    usable_bottom = height_pt - BOTTOM_MARGIN_PT
    row_h = (usable_bottom - top) // rows

    bounds: list[Bounds] = []
    for i in range(n):
        c = i % cols
        r = i // cols
        # Size each row's cells by the number of panes actually in that row,
        # so an incomplete final row stretches to fill the full width instead
        # of leaving the last column's worth of space uncovered.
        panes_in_row = min(cols, n - r * cols)
        row_col_w = width_pt // panes_in_row
        x1 = c * row_col_w
        x2 = width_pt if c == panes_in_row - 1 else (c + 1) * row_col_w
        y1 = top + r * row_h
        y2 = usable_bottom if r == rows - 1 else top + (r + 1) * row_h
        bounds.append((x1, y1, x2, y2))
    return bounds
