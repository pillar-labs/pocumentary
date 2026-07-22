import threading
import time

from pocumentary.spec import Verify
from pocumentary.verify import check_expectations, wait_for_expectations


def test_no_expectations_means_nothing_missing(tmp_path):
    assert check_expectations(str(tmp_path), Verify()) == []


def test_reports_missing_signals(tmp_path):
    v = Verify(expect=("takeover.json", "done"))
    (tmp_path / "done").write_text("")
    assert check_expectations(str(tmp_path), v) == ["takeover.json"]


def test_all_present_means_nothing_missing(tmp_path):
    (tmp_path / "a").write_text("")
    (tmp_path / "b").write_text("")
    assert check_expectations(str(tmp_path), Verify(expect=("a", "b"))) == []


def test_an_empty_file_still_counts_as_present(tmp_path):
    """Handshake files are often touched with no content; existence is the signal."""
    (tmp_path / "a").write_text("")
    assert check_expectations(str(tmp_path), Verify(expect=("a",))) == []


def test_a_missing_runtime_dir_means_everything_is_missing(tmp_path):
    absent = str(tmp_path / "never-created")
    assert check_expectations(absent, Verify(expect=("a",))) == ["a"]


def test_wait_returns_early_once_everything_arrives(tmp_path):
    v = Verify(expect=("late",), timeout=10.0)

    def touch_later():
        time.sleep(0.3)
        (tmp_path / "late").write_text("")

    threading.Thread(target=touch_later, daemon=True).start()
    started = time.monotonic()
    assert wait_for_expectations(str(tmp_path), v) == []
    assert time.monotonic() - started < 5  # returned early, did not burn the timeout


def test_wait_gives_up_at_the_timeout(tmp_path):
    started = time.monotonic()
    missing = wait_for_expectations(str(tmp_path), Verify(expect=("never",), timeout=0.3))
    assert missing == ["never"]
    assert time.monotonic() - started < 3


def test_wait_with_no_expectations_returns_immediately(tmp_path):
    started = time.monotonic()
    assert wait_for_expectations(str(tmp_path), Verify(timeout=30.0)) == []
    assert time.monotonic() - started < 1
