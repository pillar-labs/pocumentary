import pytest

from pocumentary.overlay import (
    OverlayError,
    Placement,
    build_placements,
    final_label,
    overlay_args,
    overlay_filter,
)
from pocumentary.spec import Overlay


def _ov(on, gif="e.gif", duration=3.0, scale=0.4, position="center"):
    return Overlay(on=on, gif=gif, duration=duration, scale=scale, position=position)


def test_build_placements_resolves_offsets_and_sorts_by_start():
    overlays = (
        _ov("takeover", gif="boom.gif", duration=3.0),
        _ov("start", gif="intro.gif", duration=2.0),
    )
    timeline = {"start": 0.0, "takeover": 12.5}
    placements = build_placements(overlays, timeline)
    assert [p.gif for p in placements] == ["intro.gif", "boom.gif"]  # sorted by start
    assert placements[0].start == 0.0
    assert placements[1].start == 12.5
    assert placements[1].duration == 3.0


def test_build_placements_names_missing_anchors():
    overlays = (_ov("nope"), _ov("alsomissing"))
    with pytest.raises(OverlayError) as exc:
        build_placements(overlays, {"start": 0.0})
    msg = str(exc.value)
    assert "'nope'" in msg and "'alsomissing'" in msg


def test_build_placements_empty_is_empty():
    assert build_placements((), {"start": 0.0}) == []


def test_final_label_tracks_placement_count():
    assert final_label([Placement("a.gif", 0.0, 1.0, 0.4, "center")]) == "[v0]"
    two = [Placement("a.gif", 0.0, 1.0, 0.4, "center"),
           Placement("b.gif", 2.0, 1.0, 0.4, "center")]
    assert final_label(two) == "[v1]"


def test_overlay_filter_time_gates_and_scales():
    placements = [Placement("boom.gif", 12.5, 3.0, 0.5, "center")]
    graph = overlay_filter(placements)
    # base video is input 0, the gif is input 1
    assert "[1:v][0:v]scale2ref=w='main_w*0.5'" in graph
    # on-screen window is [start, start+duration]
    assert "enable='between(t,12.5,15.5)'" in graph
    # centered position
    assert "overlay=x=(W-w)/2:y=(H-h)/2" in graph


def test_overlay_filter_chains_multiple_gifs():
    placements = [
        Placement("a.gif", 0.0, 2.0, 0.4, "top-left"),
        Placement("b.gif", 5.0, 2.0, 0.3, "bottom-right"),
    ]
    graph = overlay_filter(placements)
    # first stage feeds the second: [v0] becomes the ref for gif 2 (input [2:v])
    assert "[v0]" in graph
    assert "[2:v][v0]scale2ref=w='main_w*0.3'" in graph
    assert "overlay=x=0:y=0" in graph              # top-left
    assert "overlay=x=W-w:y=H-h" in graph          # bottom-right


def test_overlay_filter_rejects_empty():
    with pytest.raises(ValueError, match="at least one placement"):
        overlay_filter([])


def test_overlay_args_loops_each_gif_and_maps_final_stream():
    placements = [Placement("boom.gif", 1.0, 2.0, 0.4, "center")]
    args = overlay_args("take.mov", ["/tmp/boom.gif"], placements, "out.mov", "ffmpeg")
    assert args[0] == "ffmpeg"
    assert args[1:4] == ["-hide_banner", "-i", "take.mov"]
    # the gif input loops (-ignore_loop 0) but is bounded to its window end (-t 3)
    gi = args.index("/tmp/boom.gif")
    assert args[gi - 5:gi] == ["-ignore_loop", "0", "-t", "3", "-i"]
    # maps the last overlay stage's output and re-encodes
    assert args[args.index("-map") + 1] == "[v0]"
    assert "yuv420p" in args
    assert args[-1] == "out.mov"


def test_overlay_args_bounds_every_looping_gif_input():
    """Regression: an infinite `-ignore_loop 0` input must ALWAYS be capped with
    `-t` so a looping GIF can never drive a runaway (disk-filling) encode."""
    placements = [
        Placement("a.gif", 0.0, 2.0, 0.4, "center"),
        Placement("b.gif", 50.15, 3.5, 0.5, "center"),
    ]
    args = overlay_args("take.mov", ["a.gif", "b.gif"], placements, "out.mov")
    # every "-ignore_loop 0" is immediately followed by "-t <window_end>"
    for i, tok in enumerate(args):
        if tok == "-ignore_loop":
            assert args[i + 1] == "0"
            assert args[i + 2] == "-t"
            float(args[i + 3])  # a real, finite cap value
    # caps equal each window's END (start + duration)
    assert "2" in args        # a.gif: 0.0 + 2.0
    assert "53.65" in args    # b.gif: 50.15 + 3.5


def test_overlay_args_caps_output_to_source_duration():
    """With max_duration set, the OUTPUT is hard-capped with `-t` so the result
    can never be longer than the source take."""
    placements = [Placement("boom.gif", 1.0, 2.0, 0.4, "center")]
    args = overlay_args("take.mov", ["boom.gif"], placements, "out.mov",
                        "ffmpeg", max_duration=56.65)
    # the output `-t` is the last `-t` (after -filter_complex/-map), just before out
    ti = len(args) - 1 - args[::-1].index("-t")
    assert args[ti + 1] == "56.65"
    assert args.index("-filter_complex") < ti      # applies to the output, not an input
    assert args[-1] == "out.mov"


def test_overlay_args_omits_output_cap_when_unknown():
    placements = [Placement("boom.gif", 1.0, 2.0, 0.4, "center")]
    args = overlay_args("take.mov", ["boom.gif"], placements, "out.mov")
    # only the per-gif input cap exists; no output-level cap after -map
    map_i = args.index("-map")
    assert "-t" not in args[map_i:]


def test_overlay_args_rejects_length_mismatch():
    placements = [Placement("a.gif", 0.0, 1.0, 0.4, "center")]
    with pytest.raises(ValueError, match="same length"):
        overlay_args("take.mov", ["a.gif", "b.gif"], placements, "out.mov")
