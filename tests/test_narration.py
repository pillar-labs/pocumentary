import math

import pytest

from pocumentary.narration import (
    NarrationError,
    Section,
    build_sections,
    narrated_out_path,
)
from pocumentary.spec import Annotation


def test_narrated_out_path_is_a_sibling_with_suffix():
    assert narrated_out_path("/a/b/rec.mov") == "/a/b/rec-narrated.mov"


def test_build_sections_orders_by_offset_and_computes_slots():
    anns = (
        Annotation(on="server_ready", text="Up now.", duration=4.0),
        Annotation(on="start", text="Here we go.", duration=4.0),
    )
    timeline = {"start": 0.0, "server_ready": 4.44}
    sections = build_sections(anns, timeline)
    assert [s.on for s in sections] == ["start", "server_ready"]
    assert sections[0].offset == 0.0
    assert sections[0].slot == pytest.approx(4.44)
    assert sections[1].offset == pytest.approx(4.44)
    assert sections[1].slot == math.inf  # last section: unbounded


def test_build_sections_ties_keep_declaration_order():
    anns = (
        Annotation(on="start", text="First.", duration=4.0),
        Annotation(on="start", text="Second.", duration=4.0),
    )
    sections = build_sections(anns, {"start": 0.0})
    assert [s.text for s in sections] == ["First.", "Second."]
    assert sections[0].slot == 0.0  # same offset as the next → zero slot


def test_build_sections_raises_naming_missing_anchors():
    anns = (Annotation(on="never_fired", text="X.", duration=4.0),)
    with pytest.raises(NarrationError) as exc:
        build_sections(anns, {"start": 0.0})
    assert "never_fired" in str(exc.value)


from pocumentary.narration import (
    estimate_speech_seconds,
    narration_warnings,
    overlap_errors,
)
from pocumentary.spec import parse


def test_estimate_speech_seconds_rounds_up_by_11_chars_per_second():
    # 22 chars -> 2.0 s; 23 chars -> 3.0 s (ceil)
    assert estimate_speech_seconds("x" * 22) == 2.0
    assert estimate_speech_seconds("x" * 23) == 3.0


def test_narration_warnings_flags_a_line_longer_than_its_duration():
    spec = parse(
        '[layout]\nmode="columns"\n'
        '[[pane]]\ntitle="A"\ncmd="true"\n'
        '[[annotation]]\non="start"\ntext="' + "x" * 55 + '"\nduration=2.0\n'
    )
    warnings = narration_warnings(spec)
    assert len(warnings) == 1
    assert "start" in warnings[0]
    assert "2" in warnings[0]  # names the declared duration


def test_narration_warnings_silent_when_line_fits():
    spec = parse(
        '[layout]\nmode="columns"\n'
        '[[pane]]\ntitle="A"\ncmd="true"\n'
        '[[annotation]]\non="start"\ntext="short."\nduration=4.0\n'
    )
    assert narration_warnings(spec) == []


def test_overlap_errors_flags_clip_longer_than_slot_but_not_last():
    sections = [
        Section(on="start", text="a", offset=0.0, slot=3.0),
        Section(on="s2", text="b", offset=3.0, slot=math.inf),
    ]
    errors = overlap_errors(sections, durations=[5.0, 99.0])
    assert len(errors) == 1
    assert "start" in errors[0]


def test_overlap_errors_empty_when_all_fit():
    sections = [Section(on="start", text="a", offset=0.0, slot=3.0)]
    assert overlap_errors(sections, durations=[2.5]) == []


from pocumentary.narration import mix_args


def test_mix_args_builds_the_adelay_amix_mux_graph():
    args = mix_args(
        "rec.mov",
        ["/tmp/c0.wav", "/tmp/c1.wav"],
        [0.0, 4.44],
        "rec-narrated.mov",
    )
    assert args[0] == "ffmpeg"
    # inputs: the video then each clip, in order
    assert args[1:8] == [
        "-hide_banner", "-i", "rec.mov", "-i", "/tmp/c0.wav", "-i", "/tmp/c1.wav",
    ]
    fc = args[args.index("-filter_complex") + 1]
    assert fc == (
        "[1:a]adelay=0|0[a1];[2:a]adelay=4440|4440[a2];"
        "[a1][a2]amix=inputs=2:normalize=0[aout]"
    )
    # video copied, audio from the mix, overwrite
    assert args[-10:] == [
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy", "-c:a", "aac",
        "-y", "rec-narrated.mov",
    ]


def test_mix_args_single_clip_still_uses_amix():
    args = mix_args("r.mov", ["/tmp/c0.wav"], [1.2], "o.mov")
    fc = args[args.index("-filter_complex") + 1]
    assert fc == "[1:a]adelay=1200|1200[a1];[a1]amix=inputs=1:normalize=0[aout]"
