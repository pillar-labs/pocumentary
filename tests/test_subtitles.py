import pytest

from pocumentary.spec import Annotation
from pocumentary.subtitles import (
    SubtitleError,
    burn_args,
    build_srt,
    captioned_out_path,
    load_timeline,
)
from pocumentary.subtitles import _srt_timestamp


def test_srt_timestamp_formats_hms_millis():
    assert _srt_timestamp(0) == "00:00:00,000"
    assert _srt_timestamp(3661.5) == "01:01:01,500"


def test_srt_timestamp_clamps_negative():
    assert _srt_timestamp(-1.0) == "00:00:00,000"


def test_build_srt_one_cue():
    srt = build_srt((Annotation(on="start", text="hello", duration=3.0),), {"start": 0.0})
    assert srt == "1\n00:00:00,000 --> 00:00:03,000\nhello\n"


def test_build_srt_orders_by_start_and_numbers():
    anns = (
        Annotation(on="server_ready", text="second", duration=2.0),
        Annotation(on="start", text="first", duration=1.0),
    )
    srt = build_srt(anns, {"start": 0.0, "server_ready": 5.0})
    assert srt == (
        "1\n00:00:00,000 --> 00:00:01,000\nfirst\n"
        "\n"
        "2\n00:00:05,000 --> 00:00:07,000\nsecond\n"
    )


def test_build_srt_is_empty_without_annotations():
    assert build_srt((), {"start": 0.0}) == ""


def test_build_srt_raises_on_missing_anchor():
    with pytest.raises(SubtitleError, match="ghost"):
        build_srt((Annotation(on="ghost", text="x"),), {"start": 0.0})


def test_load_timeline_parses_entries():
    tl = load_timeline('[{"event":"start","offset":0.0},{"event":"server_ready","offset":3.5}]')
    assert tl == {"start": 0.0, "server_ready": 3.5}


def test_load_timeline_rejects_non_array():
    with pytest.raises(SubtitleError):
        load_timeline('{"event":"start"}')


def test_load_timeline_rejects_entry_without_offset():
    with pytest.raises(SubtitleError, match="#1"):
        load_timeline('[{"event":"start"}]')


def test_load_timeline_rejects_non_numeric_offset():
    with pytest.raises(SubtitleError, match="#1"):
        load_timeline('[{"event":"start","offset":"soon"}]')


def test_captioned_out_path():
    assert captioned_out_path("/a/b/recording.mov") == "/a/b/recording-captioned.mov"


def test_burn_args_uses_the_subtitles_filter():
    args = burn_args("in.mov", "caps.srt", "out.mov", ffmpeg="ffmpeg")
    assert args[0] == "ffmpeg"
    assert args[args.index("-i") + 1] == "in.mov"
    assert args[-1] == "out.mov"
    vf = args[args.index("-vf") + 1]
    assert vf.startswith("subtitles='caps.srt'")
    assert "force_style" in vf


def test_marker_path_is_index_suffixed_and_dotted():
    from pocumentary.subtitles import MARKER_PREFIX, marker_path

    assert marker_path("/rt", 0) == f"/rt/{MARKER_PREFIX}0"
    assert marker_path("/rt", 2) == f"/rt/{MARKER_PREFIX}2"
    assert MARKER_PREFIX.startswith(".")  # never collides with an author's signal


def test_pane_event_prefixes_title():
    from pocumentary.subtitles import pane_event

    assert pane_event("1  SERVER") == "pane:1  SERVER"


def test_timeline_watches_maps_panes_and_signals():
    from pocumentary.spec import parse
    from pocumentary.subtitles import marker_path, timeline_watches

    spec = parse(
        '[layout]\nmode = "columns"\n'
        '[[pane]]\ntitle = "1  S"\ncmd = "x"\nsignals = ["ready"]\n'
        '[[pane]]\ntitle = "2  C"\ncmd = "y"\ngate_on = "ready"\n'
    )
    w = timeline_watches(spec, "/rt")
    assert w["pane:1  S"] == marker_path("/rt", 0)
    assert w["pane:2  C"] == marker_path("/rt", 1)
    assert w["ready"].endswith("/ready")
    assert "start" not in w  # synthetic; injected by build_timeline_json


def test_build_timeline_json_injects_start_and_sorts_by_offset():
    from pocumentary.subtitles import build_timeline_json, load_timeline

    text = build_timeline_json({"server_ready": 3.5, "pane:a": 2.0})
    assert load_timeline(text) == {"start": 0.0, "pane:a": 2.0, "server_ready": 3.5}
    assert text.index('"start"') < text.index('"pane:a"') < text.index('"server_ready"')


def test_build_timeline_json_round_trips_through_load():
    from pocumentary.subtitles import build_timeline_json, load_timeline

    offsets = {"pane:x": 1.25, "sig": 4.0}
    assert load_timeline(build_timeline_json(offsets)) == {"start": 0.0, **offsets}
