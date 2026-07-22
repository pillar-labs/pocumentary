import pytest

from pocumentary.spec import Annotation, Layout, Pane, Recording, Spec, SpecError, parse, validate


def _read(name: str) -> str:
    from pathlib import Path

    return (Path(__file__).parent / "fixtures" / name).read_text()


def test_parse_valid_demo_builds_spec():
    spec = parse(_read("valid_demo.toml"))
    assert isinstance(spec, Spec)
    assert spec.recording == Recording(fps=30, out="recording-{stamp}.mov", crop="auto")
    assert spec.layout == Layout(mode="columns")
    assert len(spec.panes) == 2


def test_parse_populates_pane_fields():
    spec = parse(_read("valid_demo.toml"))
    server, adversary = spec.panes
    assert server == Pane(
        title="1  SERVER",
        cmd="python server_role.py",
        env={"DEMO_STEP_DELAY": "2.2"},
        cwd="/tmp/demo",
        gate_on=None,
        signals=("server_ready",),
        target="local",
    )
    assert adversary.gate_on == "server_ready"
    assert adversary.env == {}
    assert adversary.cwd is None


def test_parse_defaults_recording_when_absent():
    spec = parse('[layout]\nmode = "rows"\n[[pane]]\ntitle = "a"\ncmd = "echo hi"\n')
    assert spec.recording == Recording(fps=30, out="recording-{stamp}.mov", crop="auto")


def test_parse_builds_typed_annotations():
    text = (
        '[layout]\nmode = "columns"\n'
        '[[pane]]\ntitle = "a"\ncmd = "echo hi"\n'
        '[[annotation]]\non = "start"\ntext = "look here"\nduration = 3.0\n'
    )
    spec = parse(text)
    assert spec.annotations == (Annotation(on="start", text="look here", duration=3.0),)


def test_parse_annotation_duration_defaults_to_4():
    text = (
        '[layout]\nmode = "columns"\n'
        '[[pane]]\ntitle = "a"\ncmd = "echo hi"\n'
        '[[annotation]]\non = "start"\ntext = "hi"\n'
    )
    assert parse(text).annotations == (Annotation(on="start", text="hi", duration=4.0),)


def test_parse_preserves_tts_table_verbatim():
    text = (
        '[layout]\nmode = "columns"\n'
        '[[pane]]\ntitle = "a"\ncmd = "echo hi"\n'
        '[tts]\nvoice_id = "Samantha"\n'
    )
    tts = parse(text).tts
    assert isinstance(tts, Tts)
    assert tts.voice_id == "Samantha"
    assert tts.model_id == "eleven_multilingual_v2"
    assert tts.speed == 1.0
    assert tts.seed == 42


def test_parse_raises_when_annotation_missing_on_or_text():
    text = (
        '[layout]\nmode = "columns"\n'
        '[[pane]]\ntitle = "a"\ncmd = "echo hi"\n'
        '[[annotation]]\ntext = "no anchor"\n'
    )
    with pytest.raises(SpecError, match="annotation #1: both 'on' and 'text' are required"):
        parse(text)


def test_parse_raises_on_invalid_toml():
    with pytest.raises(SpecError, match="invalid TOML"):
        parse("this is = = not toml")


def test_parse_raises_when_layout_missing():
    with pytest.raises(SpecError, match=r"\[layout\]"):
        parse('[[pane]]\ntitle = "a"\ncmd = "echo hi"\n')


def test_parse_raises_when_pane_missing_cmd():
    with pytest.raises(SpecError, match="pane #1"):
        parse('[layout]\nmode = "columns"\n[[pane]]\ntitle = "a"\n')


def test_parse_accepts_integral_float_fps():
    spec = parse(
        '[recording]\nfps = 30.0\n[layout]\nmode = "columns"\n'
        '[[pane]]\ntitle = "a"\ncmd = "echo hi"\n'
    )
    assert spec.recording.fps == 30


def test_parse_rejects_non_integral_float_fps():
    with pytest.raises(SpecError, match=r"fps must be a whole number, got 29\.97"):
        parse(
            '[recording]\nfps = 29.97\n[layout]\nmode = "columns"\n'
            '[[pane]]\ntitle = "a"\ncmd = "echo hi"\n'
        )


def test_parse_rejects_non_numeric_fps():
    with pytest.raises(SpecError, match=r"fps must be an integer, got 'thirty'"):
        parse(
            '[recording]\nfps = "thirty"\n[layout]\nmode = "columns"\n'
            '[[pane]]\ntitle = "a"\ncmd = "echo hi"\n'
        )


def test_parse_rejects_bool_fps():
    with pytest.raises(SpecError, match="fps must be an integer, got True"):
        parse(
            '[recording]\nfps = true\n[layout]\nmode = "columns"\n'
            '[[pane]]\ntitle = "a"\ncmd = "echo hi"\n'
        )


def test_parse_accepts_zero_fps_without_error():
    # fps = 0 must PARSE successfully; validate() is responsible for rejecting it.
    spec = parse(
        '[recording]\nfps = 0\n[layout]\nmode = "columns"\n'
        '[[pane]]\ntitle = "a"\ncmd = "echo hi"\n'
    )
    assert spec.recording.fps == 0


def test_validate_ok_for_valid_spec():
    assert validate(parse(_read("valid_demo.toml"))) == []


def test_validate_collects_all_errors():
    errors = validate(parse(_read("invalid_demo.toml")))
    joined = "\n".join(errors)
    assert any("fps must be positive" in e for e in errors)
    assert any("columns|rows|grid" in e for e in errors)
    assert any("duplicate title" in e for e in errors)
    assert any("cmd must not be empty" in e for e in errors)
    assert any("ssh:<host>" in e for e in errors)
    assert "diagonal" in joined


def test_validate_requires_at_least_one_pane():
    spec = Spec(recording=Recording(), layout=Layout(mode="columns"), panes=())
    assert any("at least one" in e for e in validate(spec))


def test_validate_accepts_ssh_target():
    spec = Spec(
        recording=Recording(),
        layout=Layout(mode="columns"),
        panes=(Pane(title="a", cmd="echo hi", target="ssh:host.example"),),
    )
    assert validate(spec) == []


def test_validate_rejects_bad_crop():
    spec = Spec(
        recording=Recording(crop="bogus"),
        layout=Layout(mode="columns"),
        panes=(Pane(title="a", cmd="echo hi"),),
    )
    errors = validate(spec)
    assert any("'auto', 'none', or 'W:H:X:Y'" in e for e in errors)


def test_validate_rejects_whitespace_only_title():
    spec = Spec(
        recording=Recording(),
        layout=Layout(mode="columns"),
        panes=(Pane(title="   ", cmd="echo hi"),),
    )
    errors = validate(spec)
    assert any("title must not be empty" in e for e in errors)


def test_parses_v3_recording_fields():
    spec = parse(
        """
[recording]
fps = 30
hold = 9
step_delay = 2.2
keep = 3

[layout]
mode = "columns"

[[pane]]
title = "a"
cmd = "echo a"
delay = 4.0
"""
    )
    assert spec.recording.hold == 9.0
    assert spec.recording.step_delay == 2.2
    assert spec.recording.keep == 3
    assert spec.panes[0].delay == 4.0


def test_v3_fields_have_defaults():
    spec = parse(
        """
[layout]
mode = "columns"

[[pane]]
title = "a"
cmd = "echo a"
"""
    )
    assert spec.recording.hold == 6.0
    assert spec.recording.step_delay == 0.0
    assert spec.recording.keep == 0
    assert spec.panes[0].delay == 0.0


def test_non_numeric_hold_raises_spec_error():
    with pytest.raises(SpecError, match="hold"):
        parse(
            """
[recording]
hold = "soon"

[layout]
mode = "columns"

[[pane]]
title = "a"
cmd = "echo a"
"""
        )


def test_negative_hold_is_a_validation_error():
    spec = parse(
        """
[recording]
hold = -1

[layout]
mode = "columns"

[[pane]]
title = "a"
cmd = "echo a"
"""
    )
    assert "[recording] hold must not be negative, got -1.0" in validate(spec)


def test_negative_pane_delay_is_a_validation_error():
    spec = parse(
        """
[layout]
mode = "columns"

[[pane]]
title = "a"
cmd = "echo a"
delay = -2
"""
    )
    errors = validate(spec)
    assert any("delay must not be negative" in e for e in errors)


def test_negative_keep_is_a_validation_error():
    spec = parse(
        """
[recording]
keep = -1

[layout]
mode = "columns"

[[pane]]
title = "a"
cmd = "echo a"
"""
    )
    assert "[recording] keep must not be negative, got -1" in validate(spec)

def test_hold_inf_is_a_validation_error():
    spec = parse(
        """
[recording]
hold = inf

[layout]
mode = "columns"

[[pane]]
title = "a"
cmd = "echo a"
"""
    )
    errors = validate(spec)
    assert any("hold must be finite" in e for e in errors)

def test_hold_nan_is_a_validation_error():
    spec = parse(
        """
[recording]
hold = nan

[layout]
mode = "columns"

[[pane]]
title = "a"
cmd = "echo a"
"""
    )
    errors = validate(spec)
    assert any("hold must be finite" in e for e in errors)

def test_step_delay_inf_is_a_validation_error():
    spec = parse(
        """
[recording]
step_delay = inf

[layout]
mode = "columns"

[[pane]]
title = "a"
cmd = "echo a"
"""
    )
    errors = validate(spec)
    assert any("step_delay must be finite" in e for e in errors)

def test_pane_delay_nan_is_a_validation_error():
    spec = parse(
        """
[layout]
mode = "columns"

[[pane]]
title = "a"
cmd = "echo a"
delay = nan
"""
    )
    errors = validate(spec)
    assert any(
        "[[pane]] #1 ('a')" in e and "delay must be finite" in e for e in errors
    )

def test_hold_negative_infinity_produces_exactly_one_error():
    spec = parse(
        """
[recording]
hold = -inf

[layout]
mode = "columns"

[[pane]]
title = "a"
cmd = "echo a"
"""
    )
    errors = validate(spec)
    hold_errors = [e for e in errors if "hold" in e]
    assert len(hold_errors) == 1
    assert "hold must be finite" in hold_errors[0]

def test_validate_rejects_absolute_out():
    spec = Spec(
        recording=Recording(out="/tmp/pwned-{stamp}.mov"),
        layout=Layout(mode="columns"),
        panes=(Pane(title="a", cmd="echo hi"),),
    )
    errors = validate(spec)
    assert any(
        "out" in e and "/tmp/pwned-{stamp}.mov" in e for e in errors
    ), errors


def test_validate_rejects_dotdot_in_out():
    spec = Spec(
        recording=Recording(out="../../escape-{stamp}.mov"),
        layout=Layout(mode="columns"),
        panes=(Pane(title="a", cmd="echo hi"),),
    )
    errors = validate(spec)
    assert any("out" in e and ".." in e for e in errors), errors


def test_validate_accepts_plain_filename_out():
    spec = Spec(
        recording=Recording(out="rec-{stamp}.mov"),
        layout=Layout(mode="columns"),
        panes=(Pane(title="a", cmd="echo hi"),),
    )
    assert validate(spec) == []


def test_validate_accepts_relative_subdirectory_out():
    spec = Spec(
        recording=Recording(out="takes/rec-{stamp}.mov"),
        layout=Layout(mode="columns"),
        panes=(Pane(title="a", cmd="echo hi"),),
    )
    assert validate(spec) == []


def test_validate_still_accepts_a_normal_valid_spec():
    spec = parse(
        """
[recording]
hold = 6.0
step_delay = 0.5

[layout]
mode = "columns"

[[pane]]
title = "a"
cmd = "echo a"
delay = 1.5
"""
    )
    assert validate(spec) == []


def test_gate_errors_surface_through_validate():
    spec = parse(
        """
[layout]
mode = "columns"

[[pane]]
title = "a"
cmd = "x"

[[pane]]
title = "b"
cmd = "y"
gate_on = "never_emitted"
"""
    )
    assert any("never_emitted" in e for e in validate(spec))


def test_gate_timeout_defaults_and_parses():
    assert parse('[layout]\nmode="columns"\n[[pane]]\ntitle="a"\ncmd="x"\n').recording.gate_timeout == 60.0
    spec = parse(
        '[recording]\ngate_timeout = 5\n[layout]\nmode="columns"\n[[pane]]\ntitle="a"\ncmd="x"\n'
    )
    assert spec.recording.gate_timeout == 5.0


def test_non_positive_gate_timeout_is_a_validation_error():
    spec = parse(
        '[recording]\ngate_timeout = 0\n[layout]\nmode="columns"\n[[pane]]\ntitle="a"\ncmd="x"\n'
    )
    assert "[recording] gate_timeout must be positive, got 0.0" in validate(spec)


def test_gate_timeout_inf_is_a_validation_error():
    spec = parse(
        """
[recording]
gate_timeout = inf

[layout]
mode = "columns"

[[pane]]
title = "a"
cmd = "echo a"
"""
    )
    errors = validate(spec)
    gate_timeout_errors = [e for e in errors if "gate_timeout" in e]
    assert len(gate_timeout_errors) == 1
    assert "gate_timeout must be finite" in gate_timeout_errors[0]


def test_gate_timeout_nan_is_a_validation_error():
    spec = parse(
        """
[recording]
gate_timeout = nan

[layout]
mode = "columns"

[[pane]]
title = "a"
cmd = "echo a"
"""
    )
    errors = validate(spec)
    gate_timeout_errors = [e for e in errors if "gate_timeout" in e]
    assert len(gate_timeout_errors) == 1
    assert "gate_timeout must be finite" in gate_timeout_errors[0]


def test_parses_the_verify_block():
    spec = parse(
        """
[layout]
mode = "columns"

[verify]
expect = ["takeover.json"]
timeout = 30

[[pane]]
title = "a"
cmd = "x"
"""
    )
    assert spec.verify.expect == ("takeover.json",)
    assert spec.verify.timeout == 30.0


def test_verify_defaults_to_no_expectations():
    spec = parse('[layout]\nmode="columns"\n[[pane]]\ntitle="a"\ncmd="x"\n')
    assert spec.verify.expect == ()
    assert spec.verify.timeout == 60.0


def test_empty_expectation_name_is_a_validation_error():
    spec = parse(
        '[layout]\nmode="columns"\n[verify]\nexpect = ["  "]\n[[pane]]\ntitle="a"\ncmd="x"\n'
    )
    assert any("expect" in e and "empty" in e for e in validate(spec))


def test_non_positive_verify_timeout_is_a_validation_error():
    spec = parse(
        '[layout]\nmode="columns"\n[verify]\ntimeout = 0\n[[pane]]\ntitle="a"\ncmd="x"\n'
    )
    assert "[verify] timeout must be positive, got 0.0" in validate(spec)


def test_verify_timeout_inf_is_a_validation_error():
    spec = parse(
        """
[layout]
mode = "columns"

[verify]
timeout = inf

[[pane]]
title = "a"
cmd = "echo a"
"""
    )
    errors = validate(spec)
    timeout_errors = [e for e in errors if "timeout" in e and "[verify]" in e]
    assert len(timeout_errors) == 1
    assert "[verify] timeout must be finite" in timeout_errors[0]


def test_verify_timeout_nan_is_a_validation_error():
    spec = parse(
        """
[layout]
mode = "columns"

[verify]
timeout = nan

[[pane]]
title = "a"
cmd = "echo a"
"""
    )
    errors = validate(spec)
    timeout_errors = [e for e in errors if "timeout" in e and "[verify]" in e]
    assert len(timeout_errors) == 1
    assert "[verify] timeout must be finite" in timeout_errors[0]


def _spec_with_annotation(on: str, text: str = "hi", duration: float = 3.0) -> str:
    return (
        '[layout]\nmode = "columns"\n'
        '[[pane]]\ntitle = "1  SERVER"\ncmd = "sh s.sh"\nsignals = ["server_ready"]\n'
        '[[pane]]\ntitle = "2  CLIENT"\ncmd = "sh c.sh"\ngate_on = "server_ready"\n'
        f'[[annotation]]\non = "{on}"\ntext = "{text}"\nduration = {duration}\n'
    )


def test_validate_accepts_start_anchor():
    assert validate(parse(_spec_with_annotation("start"))) == []


def test_validate_accepts_signal_anchor():
    assert validate(parse(_spec_with_annotation("server_ready"))) == []


def test_validate_accepts_pane_title_anchor():
    assert validate(parse(_spec_with_annotation("pane:2  CLIENT"))) == []


def test_validate_rejects_dangling_anchor():
    errors = validate(parse(_spec_with_annotation("nope")))
    assert any("on='nope'" in e and "must be" in e for e in errors)


def test_validate_rejects_empty_text():
    errors = validate(parse(_spec_with_annotation("start", text="   ")))
    assert any("text must not be empty" in e for e in errors)


def test_validate_rejects_nonpositive_duration():
    errors = validate(parse(_spec_with_annotation("start", duration=0.0)))
    assert any("duration must be positive" in e for e in errors)


def test_validate_rejects_nonfinite_duration():
    errors = validate(parse(_spec_with_annotation("start", duration="nan")))
    assert any("duration must be finite" in e for e in errors)


from pocumentary.spec import Tts


def test_parse_tts_defaults_when_absent():
    spec = parse('[layout]\nmode="columns"\n[[pane]]\ntitle="A"\ncmd="true"\n')
    assert spec.tts is None


def test_parse_tts_typed_with_overrides():
    spec = parse(
        '[layout]\nmode="columns"\n[[pane]]\ntitle="A"\ncmd="true"\n'
        '[tts]\nvoice_id="VID"\nspeed=1.15\nseed=7\n'
    )
    assert isinstance(spec.tts, Tts)
    assert spec.tts.model_id == "eleven_multilingual_v2"
    assert spec.tts.voice_id == "VID"
    assert spec.tts.speed == 1.15
    assert spec.tts.seed == 7


def test_parse_tts_rejects_unknown_keys():
    with pytest.raises(SpecError) as exc:
        parse(
            '[layout]\nmode="columns"\n[[pane]]\ntitle="A"\ncmd="true"\n'
            '[tts]\nvioce="ryan"\n'
        )
    assert "vioce" in str(exc.value)


def test_validate_flags_nonpositive_tts_speed():
    spec = parse(
        '[layout]\nmode="columns"\n[[pane]]\ntitle="A"\ncmd="true"\n'
        '[tts]\nspeed=0\n'
    )
    errors = validate(spec)
    assert any("[tts] speed" in e for e in errors)


from pocumentary.spec import Overlay


def test_parse_overlay_defaults_and_overrides():
    spec = parse(
        '[layout]\nmode="columns"\n[[pane]]\ntitle="A"\ncmd="true"\nsignals=["boom"]\n'
        '[[overlay]]\non="start"\ngif="a.gif"\n'
        '[[overlay]]\non="boom"\ngif="https://x/y.gif"\nduration=2.5\nscale=0.6\nposition="top-left"\n'
    )
    assert len(spec.overlays) == 2
    first = spec.overlays[0]
    assert isinstance(first, Overlay)
    assert (first.gif, first.duration, first.scale, first.position) == ("a.gif", 3.0, 0.4, "center")
    second = spec.overlays[1]
    assert (second.gif, second.duration, second.scale, second.position) == (
        "https://x/y.gif", 2.5, 0.6, "top-left",
    )


def test_parse_overlay_requires_on_and_gif():
    with pytest.raises(SpecError, match="overlay #1"):
        parse('[layout]\nmode="columns"\n[[pane]]\ntitle="A"\ncmd="true"\n[[overlay]]\non="start"\n')


def test_no_overlay_block_is_empty_tuple():
    spec = parse('[layout]\nmode="columns"\n[[pane]]\ntitle="A"\ncmd="true"\n')
    assert spec.overlays == ()


def test_validate_flags_bad_overlay_scale_position_and_anchor():
    spec = parse(
        '[layout]\nmode="columns"\n[[pane]]\ntitle="A"\ncmd="true"\n'
        '[[overlay]]\non="nope"\ngif="a.gif"\nscale=2.0\nposition="middle"\n'
    )
    errors = validate(spec)
    assert any("scale must be in (0, 1]" in e for e in errors)
    assert any("position must be one of" in e for e in errors)
    assert any('on=\'nope\'' in e for e in errors)


def test_validate_flags_nonpositive_overlay_duration_and_empty_gif():
    spec = parse(
        '[layout]\nmode="columns"\n[[pane]]\ntitle="A"\ncmd="true"\n'
        '[[overlay]]\non="start"\ngif=""\nduration=0\n'
    )
    errors = validate(spec)
    assert any("gif must not be empty" in e for e in errors)
    assert any("duration must be positive" in e for e in errors)


def test_validate_accepts_valid_overlay():
    spec = parse(
        '[layout]\nmode="columns"\n[[pane]]\ntitle="A"\ncmd="true"\nsignals=["boom"]\n'
        '[[overlay]]\non="boom"\ngif="boom.gif"\nposition="bottom-right"\n'
    )
    assert validate(spec) == []
