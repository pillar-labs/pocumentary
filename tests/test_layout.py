import math

import pytest

from pocumentary.layout import BOTTOM_MARGIN_PT, MENU_BAR_PT, solve_layout


def test_columns_matches_reference_three_up():
    # 1512x982pt screen, 3 columns — the exact bounds from record_cand003.applescript.
    bounds = solve_layout(1512, 982, "columns", 3)
    assert bounds == [
        (0, 30, 504, 972),
        (504, 30, 1008, 972),
        (1008, 30, 1512, 972),
    ]


def test_columns_last_pane_absorbs_rounding_remainder():
    bounds = solve_layout(1512, 982, "columns", 5)
    # 1512 // 5 = 302; last column's right edge is the full width, not 5*302=1510.
    assert bounds[0] == (0, 30, 302, 972)
    assert bounds[-1][2] == 1512
    assert all(b[1] == MENU_BAR_PT and b[3] == 982 - BOTTOM_MARGIN_PT for b in bounds)


def test_rows_splits_vertically_full_width():
    bounds = solve_layout(1000, 830, "rows", 2)
    # usable height = 830 - 30 - 10 = 790; row height = 395.
    assert bounds == [
        (0, 30, 1000, 425),
        (0, 425, 1000, 820),
    ]


def test_grid_four_up_is_two_by_two():
    bounds = solve_layout(1512, 982, "grid", 4)
    assert len(bounds) == 4
    cols = math.ceil(math.sqrt(4))
    assert cols == 2
    assert bounds[0] == (0, 30, 756, 501)
    assert bounds[1] == (756, 30, 1512, 501)
    assert bounds[2] == (0, 501, 756, 972)
    assert bounds[3] == (756, 501, 1512, 972)


def test_grid_three_up_last_row_fills_full_width():
    # 3 panes -> ceil(sqrt(3))=2 cols, ceil(3/2)=2 rows; the last row has only
    # one pane, which must stretch across the full width rather than leaving
    # the bottom-right quadrant uncovered.
    bounds = solve_layout(1512, 982, "grid", 3)
    assert bounds == [
        (0, 30, 756, 501),
        (756, 30, 1512, 501),
        (0, 501, 1512, 972),
    ]


def test_grid_five_up_last_row_has_no_gap():
    # 5 panes -> ceil(sqrt(5))=3 cols, ceil(5/3)=2 rows; the last row has only
    # 2 panes and must together span the full width with no horizontal gap.
    bounds = solve_layout(1512, 982, "grid", 5)
    last_row = bounds[3:]
    assert len(last_row) == 2
    assert last_row[0][0] == 0
    assert last_row[-1][2] == 1512
    # No gap: each pane's right edge meets the next pane's left edge.
    for (x1, _, x2, _), (nx1, _, _, _) in zip(last_row, last_row[1:]):
        assert x2 == nx1


def test_rejects_zero_panes():
    with pytest.raises(ValueError, match="at least one pane"):
        solve_layout(1512, 982, "columns", 0)


def test_rejects_unknown_mode():
    with pytest.raises(ValueError, match="unknown layout mode"):
        solve_layout(1512, 982, "hexagon", 3)
