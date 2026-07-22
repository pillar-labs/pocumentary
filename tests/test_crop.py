import pytest

from pocumentary.crop import Crop, crop_region, resolve_crop
from pocumentary.layout import solve_layout


def test_reproduces_the_reference_crop_exactly():
    """The hand-derived DEMO_CROP from docs/reference/fastmcp-cand003/run_recording.sh.

    Three columns on the 1512x982pt reference screen at scale 2 must yield
    crop=3024:1884:0:60 — byte-identical to the value that was hard-coded by hand.
    """
    bounds = solve_layout(1512, 982, "columns", 3)
    assert crop_region(bounds, 2).to_filter() == "crop=3024:1884:0:60"


def test_crop_is_the_union_of_all_pane_bounds():
    bounds = [(0, 30, 100, 200), (100, 50, 300, 180)]
    assert crop_region(bounds, 1) == Crop(width=300, height=170, x=0, y=30)


def test_scale_multiplies_every_component():
    assert crop_region([(1, 2, 11, 22)], 2) == Crop(width=20, height=40, x=2, y=4)


def test_dimensions_are_floored_to_even():
    """Odd width/height make libx264 fail with 'Could not open encoder' under
    -pix_fmt yuv420p, so the solver must never emit them."""
    crop = crop_region([(0, 0, 51, 33)], 1)
    assert crop.width == 50
    assert crop.height == 32
    assert crop.x == 0
    assert crop.y == 0


def test_empty_bounds_is_an_error():
    with pytest.raises(ValueError, match="at least one pane"):
        crop_region([], 2)


def test_resolve_crop_none_disables_cropping():
    assert resolve_crop("none", [(0, 0, 10, 10)], 2) is None


def test_resolve_crop_auto_computes_the_region():
    bounds = solve_layout(1512, 982, "columns", 3)
    assert resolve_crop("auto", bounds, 2) == "crop=3024:1884:0:60"


def test_resolve_crop_passes_explicit_values_through_verbatim():
    """An explicit W:H:X:Y is the author's override — no scaling, no rounding."""
    assert resolve_crop("640:480:10:20", [(0, 0, 10, 10)], 2) == "crop=640:480:10:20"
