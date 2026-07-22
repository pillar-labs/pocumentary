from pathlib import Path

import pytest

from pocumentary.cli import main
from pocumentary.detect import Geometry
from pocumentary.record import RecordError

FIX = Path(__file__).parent / "fixtures"


def test_validate_ok_exit_zero(capsys):
    rc = main(["validate", str(FIX / "valid_demo.toml")])
    out = capsys.readouterr().out
    assert rc == 0
    assert "OK" in out
    assert "2 panes" in out
    assert "columns" in out


def test_validate_invalid_exit_one(capsys):
    rc = main(["validate", str(FIX / "invalid_demo.toml")])
    out = capsys.readouterr().out
    assert rc == 1
    assert "fps must be positive" in out


def test_validate_missing_file_exit_two(capsys):
    rc = main(["validate", "/no/such/demo.toml"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "not found" in err.lower()


def test_layout_generates_and_runs_applescript(monkeypatch, capsys):
    scripts = []

    def fake_detect():
        return Geometry(width_pt=1512, height_pt=982)

    def fake_run(script):
        scripts.append(script)

        class R:
            returncode = 0
            stdout = "layout: opened 2 windows"
            stderr = ""

        return R()

    monkeypatch.setattr("pocumentary.cli.sys.platform", "darwin")
    monkeypatch.setattr("pocumentary.cli.detect_geometry", fake_detect)
    monkeypatch.setattr("pocumentary.cli.run_osascript", fake_run)

    rc = main(["layout", str(FIX / "valid_demo.toml")])
    out = capsys.readouterr().out
    assert rc == 0
    assert "opened 2 windows" in out
    assert scripts and scripts[0].count("my openWindow(") == 2
    assert "{0, 30, 756, 972}" in scripts[0]


def test_layout_invalid_spec_exit_one(monkeypatch, capsys):
    monkeypatch.setattr("pocumentary.cli.sys.platform", "darwin")
    rc = main(["layout", str(FIX / "invalid_demo.toml")])
    assert rc == 1
    assert "fps must be positive" in capsys.readouterr().out


def test_layout_off_macos_exit_two(monkeypatch, capsys):
    monkeypatch.setattr("pocumentary.cli.sys.platform", "linux")
    rc = main(["layout", str(FIX / "valid_demo.toml")])
    assert rc == 2
    assert "macos" in capsys.readouterr().err.lower()


def test_layout_osascript_failure_exit_two(monkeypatch, capsys):
    def fake_detect():
        return Geometry(width_pt=1512, height_pt=982)

    def fake_run(script):
        class R:
            returncode = 1
            stdout = ""
            stderr = "execution error: Not authorized to send Apple events to Finder. (-1743)"

        return R()

    monkeypatch.setattr("pocumentary.cli.sys.platform", "darwin")
    monkeypatch.setattr("pocumentary.cli.detect_geometry", fake_detect)
    monkeypatch.setattr("pocumentary.cli.run_osascript", fake_run)

    rc = main(["layout", str(FIX / "valid_demo.toml")])
    captured = capsys.readouterr()
    assert rc == 2
    assert "-1743" in captured.err or "Not authorized" in captured.err
    assert "opened" not in captured.out


def test_layout_detect_failure_exit_two(monkeypatch, capsys):
    def fake_detect():
        raise RuntimeError("osascript failed: Not authorized to send Apple events to Finder. (-1743)")

    monkeypatch.setattr("pocumentary.cli.sys.platform", "darwin")
    monkeypatch.setattr("pocumentary.cli.detect_geometry", fake_detect)

    rc = main(["layout", str(FIX / "valid_demo.toml")])
    err = capsys.readouterr().err
    assert rc == 2
    assert "-1743" in err or "Not authorized" in err


def test_layout_detect_bad_output_exit_two(monkeypatch, capsys):
    def fake_detect():
        raise ValueError("expected 4 comma-separated ints, got: ''")

    monkeypatch.setattr("pocumentary.cli.sys.platform", "darwin")
    monkeypatch.setattr("pocumentary.cli.detect_geometry", fake_detect)

    rc = main(["layout", str(FIX / "valid_demo.toml")])
    err = capsys.readouterr().err
    assert rc == 2
    assert "expected 4 comma-separated ints" in err


def test_validate_malformed_toml_exit_one(tmp_path, capsys):
    bad = tmp_path / "bad.toml"
    bad.write_text("this is = = not toml")
    rc = main(["validate", str(bad)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "invalid TOML" in out


def test_record_rejects_a_missing_spec(capsys):
    assert main(["record", "/nope/demo.toml"]) == 2
    assert "not found" in capsys.readouterr().err


def test_record_rejects_an_invalid_spec(tmp_path, capsys):
    spec = tmp_path / "demo.toml"
    spec.write_text('[layout]\nmode = "sideways"\n\n[[pane]]\ntitle = "a"\ncmd = "x"\n')
    assert main(["record", str(spec)]) == 1


def test_record_reports_a_missing_ffmpeg(tmp_path, monkeypatch, capsys):
    spec = tmp_path / "demo.toml"
    spec.write_text('[layout]\nmode = "columns"\n\n[[pane]]\ntitle = "a"\ncmd = "x"\n')
    monkeypatch.setattr("pocumentary.cli.is_macos", lambda: True)
    monkeypatch.setattr("pocumentary.cli.which", lambda name: None)
    assert main(["record", str(spec)]) == 2
    assert "ffmpeg" in capsys.readouterr().err


def test_record_happy_path_prints_the_movie_path(tmp_path, monkeypatch, capsys):
    spec = tmp_path / "demo.toml"
    spec.write_text(
        '[recording]\nout = "take-{stamp}.mov"\n\n'
        '[layout]\nmode = "columns"\n\n[[pane]]\ntitle = "a"\ncmd = "x"\n'
    )
    monkeypatch.setattr("pocumentary.cli.which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr("pocumentary.cli.is_macos", lambda: True)
    monkeypatch.setattr(
        "pocumentary.cli.detect_geometry", lambda: Geometry(width_pt=1512, height_pt=982)
    )
    monkeypatch.setattr("pocumentary.cli.detect_scale", lambda: 2)
    monkeypatch.setattr("pocumentary.cli.detect_screen_device_index", lambda ffmpeg="ffmpeg": 3)
    taken = {}
    monkeypatch.setattr("pocumentary.cli.run_take", lambda *a, **k: taken.update(k))

    assert main(["record", str(spec)]) == 0
    out = capsys.readouterr().out
    assert "take-" in out and ".mov" in out
    # the movie path the CLI printed is the one it actually handed the recorder
    assert taken["out_path"].endswith(".mov")
    assert Path(taken["out_path"]).name in out


def test_record_surfaces_a_record_error_as_exit_2(tmp_path, monkeypatch, capsys):
    spec = tmp_path / "demo.toml"
    spec.write_text('[layout]\nmode = "columns"\n\n[[pane]]\ntitle = "a"\ncmd = "x"\n')
    monkeypatch.setattr("pocumentary.cli.which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr("pocumentary.cli.is_macos", lambda: True)
    monkeypatch.setattr(
        "pocumentary.cli.detect_geometry", lambda: Geometry(width_pt=1512, height_pt=982)
    )
    monkeypatch.setattr("pocumentary.cli.detect_scale", lambda: 2)
    monkeypatch.setattr("pocumentary.cli.detect_screen_device_index", lambda ffmpeg="ffmpeg": 3)

    def boom(*a, **k):
        raise RecordError("osascript failed: -1743 not authorised")

    monkeypatch.setattr("pocumentary.cli.run_take", boom)
    assert main(["record", str(spec)]) == 2
    assert "1743" in capsys.readouterr().err


def test_dryrun_rejects_a_missing_spec(capsys):
    assert main(["dryrun", "/nope/demo.toml"]) == 2
    assert "not found" in capsys.readouterr().err


def test_dryrun_rejects_an_invalid_spec(tmp_path):
    spec = tmp_path / "demo.toml"
    spec.write_text('[layout]\nmode = "sideways"\n\n[[pane]]\ntitle = "a"\ncmd = "x"\n')
    assert main(["dryrun", str(spec)]) == 1


def test_dryrun_passes_when_expectations_are_met(tmp_path, capsys):
    spec = tmp_path / "demo.toml"
    spec.write_text(
        '[layout]\nmode = "columns"\n\n'
        '[verify]\nexpect = ["done"]\ntimeout = 10\n\n'
        '[[pane]]\ntitle = "a"\ncmd = \': > "$DEMO_RUNTIME_DIR/done"\'\n'
    )
    assert main(["dryrun", str(spec), "--runtime-dir", str(tmp_path / "rt")]) == 0
    assert "PASS" in capsys.readouterr().out


def test_dryrun_fails_loudly_when_expectations_are_unmet(tmp_path, capsys):
    spec = tmp_path / "demo.toml"
    spec.write_text(
        '[layout]\nmode = "columns"\n\n'
        '[verify]\nexpect = ["never"]\ntimeout = 0.3\n\n'
        '[[pane]]\ntitle = "a"\ncmd = "true"\n'
    )
    assert main(["dryrun", str(spec), "--runtime-dir", str(tmp_path / "rt")]) == 1
    captured = capsys.readouterr()
    assert "FAIL" in captured.out or "FAIL" in captured.err
    assert "never" in captured.out + captured.err


def test_dryrun_reports_a_gate_timeout(tmp_path, capsys):
    spec = tmp_path / "demo.toml"
    spec.write_text(
        '[recording]\ngate_timeout = 0.3\n\n[layout]\nmode = "columns"\n\n'
        '[[pane]]\ntitle = "a"\ncmd = "true"\nsignals = ["ready"]\n\n'
        '[[pane]]\ntitle = "b"\ncmd = "true"\ngate_on = "ready"\n'
    )
    assert main(["dryrun", str(spec), "--runtime-dir", str(tmp_path / "rt")]) == 1
    assert "ready" in capsys.readouterr().out


def test_dryrun_prints_pane_output_on_failure(tmp_path, capsys):
    """A bare FAIL is useless; the operator needs to see why the pane died."""
    spec = tmp_path / "demo.toml"
    spec.write_text(
        '[layout]\nmode = "columns"\n\n'
        '[verify]\nexpect = ["never"]\ntimeout = 0.3\n\n'
        '[[pane]]\ntitle = "a"\ncmd = "echo diagnostic-breadcrumb"\n'
    )
    main(["dryrun", str(spec), "--runtime-dir", str(tmp_path / "rt")])
    assert "diagnostic-breadcrumb" in capsys.readouterr().out


def test_dryrun_needs_no_macos(tmp_path, monkeypatch):
    """R5/CI: dryrun must work off-platform. Force the guard closed and prove it."""
    monkeypatch.setattr("pocumentary.cli.is_macos", lambda: False)
    spec = tmp_path / "demo.toml"
    spec.write_text('[layout]\nmode = "columns"\n\n[[pane]]\ntitle = "a"\ncmd = "true"\n')
    assert main(["dryrun", str(spec), "--runtime-dir", str(tmp_path / "rt")]) == 0


def test_record_exits_1_when_verification_fails(tmp_path, monkeypatch, capsys):
    spec = tmp_path / "demo.toml"
    spec.write_text(
        '[recording]\nout = "t-{stamp}.mov"\n\n[layout]\nmode = "columns"\n\n'
        '[verify]\nexpect = ["never"]\n\n[[pane]]\ntitle = "a"\ncmd = "true"\n'
    )
    monkeypatch.setattr("pocumentary.cli.which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr("pocumentary.cli.is_macos", lambda: True)
    monkeypatch.setattr(
        "pocumentary.cli.detect_geometry", lambda: Geometry(width_pt=1512, height_pt=982)
    )
    monkeypatch.setattr("pocumentary.cli.detect_scale", lambda: 2)
    monkeypatch.setattr("pocumentary.cli.detect_screen_device_index", lambda ffmpeg="ffmpeg": 3)
    monkeypatch.setattr("pocumentary.cli.run_take", lambda *a, **k: None)

    assert main(["record", str(spec), "--runtime-dir", str(tmp_path / "rt")]) == 1
    out = capsys.readouterr().out
    assert ".mov" in out  # the artifact is still reported — it shows the failure
    assert "never" in out


def test_anchor_cwds_defaults_unset_to_the_spec_dir(tmp_path):
    from pocumentary.cli import _anchor_cwds
    from pocumentary.spec import Layout, Pane, Recording, Spec

    spec = Spec(recording=Recording(), layout=Layout(mode="columns"), panes=(Pane(title="a", cmd="x"),))
    anchored = _anchor_cwds(spec, str(tmp_path / "demo.toml"))
    assert anchored.panes[0].cwd == str((tmp_path / "demo.toml").resolve().parent)


def test_anchor_cwds_resolves_relative_against_the_spec_dir(tmp_path):
    from pocumentary.cli import _anchor_cwds
    from pocumentary.spec import Layout, Pane, Recording, Spec

    spec = Spec(recording=Recording(), layout=Layout(mode="columns"), panes=(Pane(title="a", cmd="x", cwd="roles"),))
    anchored = _anchor_cwds(spec, str(tmp_path / "demo.toml"))
    assert anchored.panes[0].cwd == str((tmp_path / "demo.toml").resolve().parent / "roles")


def test_anchor_cwds_leaves_an_absolute_cwd_unchanged(tmp_path):
    from pocumentary.cli import _anchor_cwds
    from pocumentary.spec import Layout, Pane, Recording, Spec

    spec = Spec(recording=Recording(), layout=Layout(mode="columns"), panes=(Pane(title="a", cmd="x", cwd="/abs/where"),))
    anchored = _anchor_cwds(spec, str(tmp_path / "demo.toml"))
    assert anchored.panes[0].cwd == "/abs/where"


def test_layout_anchors_relative_cwd_to_the_spec_dir(tmp_path, monkeypatch):
    """pocumentary layout opens Terminal windows that start in $HOME, so a relative
    pane cwd must be anchored to the spec's directory just as record/dryrun do."""
    scripts = []

    def fake_run(script):
        scripts.append(script)

        class R:
            returncode = 0
            stdout = "layout: opened 1 windows"
            stderr = ""

        return R()

    monkeypatch.setattr("pocumentary.cli.sys.platform", "darwin")
    monkeypatch.setattr("pocumentary.cli.detect_geometry", lambda: Geometry(width_pt=1512, height_pt=982))
    monkeypatch.setattr("pocumentary.cli.run_osascript", fake_run)

    spec = tmp_path / "demo.toml"
    spec.write_text(
        '[layout]\nmode = "columns"\n\n[[pane]]\ntitle = "a"\ncmd = "sh roles/x.sh"\ncwd = "roles"\n'
    )
    rc = main(["layout", str(spec)])
    assert rc == 0
    expected = f"cd {str((tmp_path / 'demo.toml').resolve().parent / 'roles')}"
    assert scripts and expected in scripts[0], scripts[0]


def test_explain_prints_reference_and_exits_zero(capsys):
    assert main(["explain"]) == 0
    out = capsys.readouterr().out
    assert "demo.toml" in out
    assert "[[pane]]" in out


def test_docs_is_an_alias_for_explain(capsys):
    assert main(["docs"]) == 0
    assert "[recording]" in capsys.readouterr().out


def test_scaffold_creates_the_starter_files(tmp_path):
    target = tmp_path / "mydemo"
    assert main(["scaffold", str(target)]) == 0
    assert (target / "demo.toml").exists()
    assert (target / "roles" / "server.sh").exists()
    assert (target / "roles" / "client.sh").exists()


def test_scaffolded_demo_validates(tmp_path):
    target = tmp_path / "d"
    main(["scaffold", str(target)])
    assert main(["validate", str(target / "demo.toml")]) == 0


def test_scaffolded_demo_passes_dryrun(tmp_path):
    """The whole point of V5 (R7.1): a scaffolded demo runs green with no edits.
    This executes the emitted role scripts headlessly through the real gate."""
    target = tmp_path / "d"
    main(["scaffold", str(target)])
    rc = main(
        ["dryrun", str(target / "demo.toml"), "--runtime-dir", str(tmp_path / "rt")]
    )
    assert rc == 0
    assert (tmp_path / "rt" / "handoff.json").exists()


def test_scaffold_refuses_to_overwrite(tmp_path, capsys):
    target = tmp_path / "d"
    assert main(["scaffold", str(target)]) == 0
    assert main(["scaffold", str(target)]) == 2
    assert "refusing to overwrite" in capsys.readouterr().err


def _annotate_demo(tmp_path, with_annotation=True):
    ann = (
        '[[annotation]]\non = "start"\ntext = "hello"\nduration = 2.0\n'
        if with_annotation
        else ""
    )
    toml = tmp_path / "demo.toml"
    toml.write_text(
        '[layout]\nmode = "columns"\n[[pane]]\ntitle = "a"\ncmd = "echo hi"\n' + ann
    )
    mov = tmp_path / "rec.mov"
    mov.write_text("fake-movie-bytes")
    return toml, mov


def test_annotate_burns_captions(tmp_path, monkeypatch):
    import pocumentary.cli as cli

    toml, mov = _annotate_demo(tmp_path)
    (tmp_path / "rec.mov.timeline.json").write_text('[{"event":"start","offset":0.0}]')
    monkeypatch.setattr(cli, "which", lambda name: "/usr/bin/ffmpeg")

    calls = {}

    def fake_burn(mov_path, srt_text, out_path, ffmpeg="ffmpeg"):
        calls["srt"] = srt_text
        calls["out"] = out_path
        from pathlib import Path
        Path(out_path).write_text("captioned")

    monkeypatch.setattr(cli, "burn_subtitles", fake_burn)

    rc = cli.main(["annotate", str(toml), str(mov)])
    assert rc == 0
    assert "hello" in calls["srt"]
    assert calls["out"] == str(tmp_path / "rec-captioned.mov")


def test_annotate_errors_when_no_annotations(tmp_path):
    from pocumentary.cli import main

    toml, mov = _annotate_demo(tmp_path, with_annotation=False)
    assert main(["annotate", str(toml), str(mov)]) == 2


def test_annotate_errors_when_recording_missing(tmp_path):
    from pocumentary.cli import main

    toml, _ = _annotate_demo(tmp_path)
    assert main(["annotate", str(toml), str(tmp_path / "nope.mov")]) == 2


def test_annotate_errors_when_timeline_missing(tmp_path):
    from pocumentary.cli import main

    toml, mov = _annotate_demo(tmp_path)  # no .timeline.json written
    assert main(["annotate", str(toml), str(mov)]) == 2


def _overlay_demo(tmp_path, *, with_annotation=False, gif="boom.gif", on="start"):
    ann = '[[annotation]]\non="start"\ntext="hello"\nduration=2.0\n' if with_annotation else ""
    toml = tmp_path / "demo.toml"
    toml.write_text(
        '[layout]\nmode="columns"\n[[pane]]\ntitle="a"\ncmd="echo hi"\nsignals=["boom"]\n'
        + ann
        + f'[[overlay]]\non="{on}"\ngif="{gif}"\nduration=3.0\nscale=0.5\n'
    )
    mov = tmp_path / "rec.mov"
    mov.write_text("fake-movie-bytes")
    import json
    with open(f"{mov}.timeline.json", "w") as f:
        json.dump([{"event": "start", "offset": 0.0}, {"event": "boom", "offset": 9.0}], f)
    return toml, mov


def test_annotate_overlays_only_burns_gif(tmp_path, monkeypatch):
    import pocumentary.cli as cli

    (tmp_path / "boom.gif").write_bytes(b"GIF89a")
    toml, mov = _overlay_demo(tmp_path)
    monkeypatch.setattr(cli, "which", lambda name: "/usr/bin/ffmpeg")

    calls = {}

    def fake_overlays(mov_path, gif_paths, placements, out_path, ffmpeg="ffmpeg", ffprobe="ffprobe"):
        calls["gifs"] = gif_paths
        calls["placements"] = placements
        calls["out"] = out_path
        Path(out_path).write_text("burned")

    burned_subtitles = {"called": False}
    monkeypatch.setattr(cli, "burn_overlays", fake_overlays)
    monkeypatch.setattr(cli, "burn_subtitles",
                        lambda *a, **k: burned_subtitles.__setitem__("called", True))

    rc = cli.main(["annotate", str(toml), str(mov)])
    assert rc == 0
    assert burned_subtitles["called"] is False        # no captions in this demo
    assert calls["out"] == str(tmp_path / "rec-captioned.mov")
    assert calls["gifs"] == [str(tmp_path / "boom.gif")]
    assert calls["placements"][0].start == 0.0


def test_annotate_both_captions_and_overlays_two_pass(tmp_path, monkeypatch):
    import pocumentary.cli as cli

    (tmp_path / "boom.gif").write_bytes(b"GIF89a")
    toml, mov = _overlay_demo(tmp_path, with_annotation=True)
    monkeypatch.setattr(cli, "which", lambda name: "/usr/bin/ffmpeg")

    order = []

    def fake_subs(mov_path, srt_text, out_path, ffmpeg="ffmpeg"):
        order.append(("subs", mov_path, out_path))
        Path(out_path).write_text("captioned")

    def fake_overlays(mov_path, gif_paths, placements, out_path, ffmpeg="ffmpeg", ffprobe="ffprobe"):
        order.append(("overlays", mov_path, out_path))
        Path(out_path).write_text("burned")

    monkeypatch.setattr(cli, "burn_subtitles", fake_subs)
    monkeypatch.setattr(cli, "burn_overlays", fake_overlays)

    rc = cli.main(["annotate", str(toml), str(mov)])
    assert rc == 0
    # captions first (to a temp), then overlays consume that temp -> final out
    assert [step[0] for step in order] == ["subs", "overlays"]
    subs_out = order[0][2]
    overlays_in = order[1][1]
    assert subs_out == overlays_in                       # temp threads through
    assert order[1][2] == str(tmp_path / "rec-captioned.mov")


def test_annotate_missing_local_gif_is_exit_2(tmp_path, monkeypatch, capsys):
    import pocumentary.cli as cli

    toml, mov = _overlay_demo(tmp_path, gif="missing.gif")  # file never created
    monkeypatch.setattr(cli, "which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(cli, "burn_overlays", lambda *a, **k: None)

    rc = cli.main(["annotate", str(toml), str(mov)])
    assert rc == 2
    assert "gif not found" in capsys.readouterr().err


def test_annotate_overlay_anchor_absent_from_timeline_is_exit_2(tmp_path, monkeypatch, capsys):
    import pocumentary.cli as cli

    (tmp_path / "boom.gif").write_bytes(b"GIF89a")
    # anchor on the "boom" signal, but write a timeline WITHOUT it
    toml, mov = _overlay_demo(tmp_path, on="boom")
    import json
    with open(f"{mov}.timeline.json", "w") as f:
        json.dump([{"event": "start", "offset": 0.0}], f)
    monkeypatch.setattr(cli, "which", lambda name: "/usr/bin/ffmpeg")

    rc = cli.main(["annotate", str(toml), str(mov)])
    assert rc == 2
    assert "no timeline entry for overlay anchor" in capsys.readouterr().err


def test_resolve_gifs_local_and_url(tmp_path, monkeypatch):
    import pocumentary.cli as cli
    from pocumentary.overlay import Placement

    (tmp_path / "local.gif").write_bytes(b"GIF89a")
    spec_path = str(tmp_path / "demo.toml")

    fetched = {}

    def fake_fetch(url, dest):
        fetched["url"] = url
        fetched["dest"] = dest
        with open(dest, "wb") as f:
            f.write(b"downloaded")

    monkeypatch.setattr(cli, "_fetch_gif", fake_fetch)

    placements = [
        Placement("local.gif", 0.0, 1.0, 0.4, "center"),
        Placement("https://x/y.gif", 2.0, 1.0, 0.4, "center"),
    ]
    dl_dir = tmp_path / "dl"
    dl_dir.mkdir()
    paths = cli._resolve_gifs(placements, spec_path, str(dl_dir))
    assert paths[0] == str(tmp_path / "local.gif")           # resolved against spec dir
    assert paths[1] == str(dl_dir / "overlay-001.gif")       # downloaded into tmp_dir
    assert fetched["url"] == "https://x/y.gif"


def test_resolve_gifs_missing_local_raises(tmp_path):
    import pocumentary.cli as cli
    from pocumentary.overlay import Placement

    with pytest.raises(FileNotFoundError, match="gif not found"):
        cli._resolve_gifs(
            [Placement("nope.gif", 0.0, 1.0, 0.4, "center")],
            str(tmp_path / "demo.toml"), str(tmp_path),
        )


def _write_timeline(mov_path):
    import json
    with open(f"{mov_path}.timeline.json", "w") as f:
        json.dump([{"event": "start", "offset": 0.0},
                   {"event": "server_ready", "offset": 4.44}], f)


_NARRATE_TOML = (
    '[layout]\nmode="columns"\n'
    '[[pane]]\ntitle="S"\ncmd="true"\nsignals=["server_ready"]\n'
    '[[annotation]]\non="start"\ntext="Here we go now."\nduration=4.0\n'
    '[[annotation]]\non="server_ready"\ntext="It is up now."\nduration=4.0\n'
)


def test_narrate_happy_path(tmp_path, monkeypatch, capsys):
    from pocumentary import cli
    from pocumentary.narration import narrated_out_path
    from pocumentary.synth import Clip

    spec_path = tmp_path / "demo.toml"
    spec_path.write_text(_NARRATE_TOML)
    mov = tmp_path / "rec.mov"
    mov.write_bytes(b"fake-mov")
    _write_timeline(str(mov))

    # stub the engine (synth) and the ffmpeg mux (postprod) — clips fit their slots
    seen = {}

    def _fake_synth(sections, tts, out_dir, api_key, ffprobe):
        seen["api_key"] = api_key
        return [Clip(path=f"{out_dir}/clip-{i:03d}.mp3", duration=2.0)
                for i, _ in enumerate(sections)]

    mixed = {}

    def _fake_mix(mov_path, clip_paths, offsets, out_path, ffmpeg):
        mixed["out"] = out_path

    monkeypatch.setenv("ELEVENLABS_API_KEY", "sk_test")
    monkeypatch.setattr(cli, "synthesize", _fake_synth)
    monkeypatch.setattr(cli, "mix_narration", _fake_mix)
    monkeypatch.setattr(cli, "which", lambda name: f"/usr/bin/{name}")

    rc = cli._cmd_narrate(str(spec_path), str(mov))
    assert rc == 0
    assert seen["api_key"] == "sk_test"
    assert mixed["out"] == narrated_out_path(str(mov))
    assert "narrated:" in capsys.readouterr().out


def test_narrate_hard_errors_on_overlap(tmp_path, monkeypatch, capsys):
    from pocumentary import cli
    from pocumentary.synth import Clip

    spec_path = tmp_path / "demo.toml"
    spec_path.write_text(_NARRATE_TOML)
    mov = tmp_path / "rec.mov"
    mov.write_bytes(b"fake-mov")
    _write_timeline(str(mov))

    # first clip is 9s but only 4.44s until the next event → overlap
    def _fake_synth(sections, tts, out_dir, api_key, ffprobe):
        durs = [9.0, 2.0]
        return [Clip(path=f"{out_dir}/clip-{i:03d}.mp3", duration=durs[i])
                for i, _ in enumerate(sections)]

    called = {"mix": False}
    monkeypatch.setenv("ELEVENLABS_API_KEY", "sk_test")
    monkeypatch.setattr(cli, "synthesize", _fake_synth)
    monkeypatch.setattr(cli, "mix_narration",
                        lambda *a, **k: called.__setitem__("mix", True))
    monkeypatch.setattr(cli, "which", lambda name: f"/usr/bin/{name}")

    rc = cli._cmd_narrate(str(spec_path), str(mov))
    assert rc == 2
    assert called["mix"] is False  # never muxed a half-narrated artifact
    assert "until the next event" in capsys.readouterr().err


def test_narrate_missing_timeline_is_exit_2(tmp_path, capsys):
    from pocumentary import cli
    spec_path = tmp_path / "demo.toml"
    spec_path.write_text(_NARRATE_TOML)
    mov = tmp_path / "rec.mov"
    mov.write_bytes(b"fake-mov")  # no .timeline.json sidecar
    rc = cli._cmd_narrate(str(spec_path), str(mov))
    assert rc == 2
    assert "timeline" in capsys.readouterr().err


def test_validate_prints_narration_warning(tmp_path, capsys):
    from pocumentary import cli
    spec_path = tmp_path / "demo.toml"
    spec_path.write_text(
        '[layout]\nmode="columns"\n[[pane]]\ntitle="A"\ncmd="true"\n'
        '[[annotation]]\non="start"\ntext="' + "x" * 60 + '"\nduration=2.0\n'
    )
    rc = cli._cmd_validate(str(spec_path))
    assert rc == 0  # warnings never fail validate
    assert "warning:" in capsys.readouterr().err


def test_parse_env_file_reads_key_value_pairs():
    from pocumentary.cli import _parse_env_file

    parsed = _parse_env_file(
        "# a comment\n"
        "\n"
        "export ELEVENLABS_API_KEY=sk_plain\n"
        'QUOTED="sk_quoted"\n'
        "SINGLE='sk_single'\n"
        "no_equals_line\n"
    )
    assert parsed["ELEVENLABS_API_KEY"] == "sk_plain"
    assert parsed["QUOTED"] == "sk_quoted"
    assert parsed["SINGLE"] == "sk_single"
    assert "no_equals_line" not in parsed


def test_resolve_api_key_prefers_env_var(tmp_path, monkeypatch):
    from pocumentary.cli import _resolve_api_key

    monkeypatch.setenv("ELEVENLABS_API_KEY", "sk_from_env")
    (tmp_path / ".env").write_text("ELEVENLABS_API_KEY=sk_from_file\n")
    spec_path = tmp_path / "demo.toml"
    spec_path.write_text("[layout]\nmode='columns'\n")
    assert _resolve_api_key(str(spec_path)) == "sk_from_env"


def test_resolve_api_key_falls_back_to_dotenv_beside_spec(tmp_path, monkeypatch):
    from pocumentary.cli import _resolve_api_key

    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    (tmp_path / ".env").write_text("ELEVENLABS_API_KEY=sk_from_file\n")
    spec_path = tmp_path / "demo.toml"
    spec_path.write_text("[layout]\nmode='columns'\n")
    assert _resolve_api_key(str(spec_path)) == "sk_from_file"


def test_resolve_api_key_returns_none_when_absent(tmp_path, monkeypatch):
    from pocumentary.cli import _resolve_api_key

    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    spec_path = tmp_path / "demo.toml"
    spec_path.write_text("[layout]\nmode='columns'\n")
    assert _resolve_api_key(str(spec_path)) is None


def test_narrate_falls_back_to_local_when_no_api_key(tmp_path, monkeypatch, capsys):
    from pocumentary import cli
    from pocumentary.synth import Clip

    spec_path = tmp_path / "demo.toml"
    spec_path.write_text(_NARRATE_TOML)
    mov = tmp_path / "rec.mov"
    mov.write_bytes(b"fake-mov")
    _write_timeline(str(mov))

    seen = {}

    def _fake_synth(sections, tts, out_dir, api_key, ffprobe):
        seen["api_key"] = api_key
        return [Clip(path=f"{out_dir}/clip-{i:03d}.wav", duration=2.0)
                for i, _ in enumerate(sections)]

    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "synthesize", _fake_synth)
    monkeypatch.setattr(cli, "mix_narration", lambda *a, **k: None)
    monkeypatch.setattr(cli, "which", lambda name: f"/usr/bin/{name}")

    rc = cli._cmd_narrate(str(spec_path), str(mov))
    assert rc == 0
    assert seen["api_key"] is None          # fallback path: no key passed through
    assert "falling back to on-device" in capsys.readouterr().err
