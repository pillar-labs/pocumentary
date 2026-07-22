import pytest

from pocumentary.naming import STAMP_FORMAT, expand_out, out_glob, select_prunable


def test_expands_the_stamp_placeholder():
    assert expand_out("recording-{stamp}.mov", "20260721-143000") == (
        "recording-20260721-143000.mov"
    )


def test_template_without_a_placeholder_is_used_verbatim():
    assert expand_out("fixed.mov", "20260721-143000") == "fixed.mov"


def test_expands_every_occurrence():
    assert expand_out("{stamp}/take-{stamp}.mov", "S") == "S/take-S.mov"


def test_out_glob_matches_any_stamp():
    assert out_glob("recording-{stamp}.mov") == "recording-*.mov"


def test_stamp_format_sorts_chronologically_as_text():
    """select_prunable relies on lexicographic order equalling chronological
    order, which %Y%m%d-%H%M%S guarantees (fixed width, most-significant first)."""
    assert STAMP_FORMAT == "%Y%m%d-%H%M%S"
    assert "20260721-090000" < "20260721-143000" < "20260722-010000"


def test_keeps_the_newest_and_returns_the_rest():
    paths = [
        "/t/rec-20260721-090000.mov",
        "/t/rec-20260721-143000.mov",
        "/t/rec-20260722-010000.mov",
    ]
    assert select_prunable(paths, keep=1) == [
        "/t/rec-20260721-090000.mov",
        "/t/rec-20260721-143000.mov",
    ]


def test_unsorted_input_is_sorted_before_selecting():
    paths = ["/t/rec-20260722-010000.mov", "/t/rec-20260721-090000.mov"]
    assert select_prunable(paths, keep=1) == ["/t/rec-20260721-090000.mov"]


def test_keep_zero_means_keep_everything():
    """0 is the default: never delete anything unless the author opts in."""
    assert select_prunable(["/t/a.mov", "/t/b.mov"], keep=0) == []


def test_negative_keep_also_deletes_nothing():
    assert select_prunable(["/t/a.mov"], keep=-1) == []


def test_nothing_to_prune_when_under_the_limit():
    assert select_prunable(["/t/a.mov"], keep=3) == []
