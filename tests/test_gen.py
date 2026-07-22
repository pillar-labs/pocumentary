import re

import pytest

from pocumentary.gen import (
    BACKDROP_TITLE,
    CLOSEWINDOWS_HANDLER,
    OPENWINDOW_HANDLER,
    WAITFORFILE_HANDLER,
    escape_applescript_string,
    generate_backdrop_applescript,
    generate_cleanup_applescript,
    generate_layout_applescript,
    generate_record_applescript,
)
from pocumentary.spec import Layout, Pane, Recording, Spec, Verify, validate


def _spec(*panes: Pane) -> Spec:
    return Spec(recording=Recording(), layout=Layout(mode="columns"), panes=panes)


def test_escape_handles_quotes_and_backslashes():
    assert escape_applescript_string('say "hi"') == 'say \\"hi\\"'
    assert escape_applescript_string("a\\b") == "a\\\\b"


def test_generate_emits_one_openwindow_call_per_pane():
    spec = _spec(
        Pane(title="1 SERVER", cmd="echo a"),
        Pane(title="2 ADVERSARY", cmd="echo b"),
    )
    script = generate_layout_applescript(spec, [(0, 30, 504, 972), (504, 30, 1008, 972)])
    assert script.count("my openWindow(") == 2


def test_generate_embeds_bounds_title_and_baked_command():
    spec = _spec(Pane(title="1 SERVER", cmd="python role.py", env={"K": "v"}, cwd="/tmp/d"))
    script = generate_layout_applescript(spec, [(0, 30, 504, 972)])
    assert "{0, 30, 504, 972}" in script
    assert '"1 SERVER"' in script
    assert "clear; cd /tmp/d; K=v python role.py" in script


def test_generate_includes_cmd_n_first_handler():
    spec = _spec(Pane(title="a", cmd="echo hi"))
    script = generate_layout_applescript(spec, [(0, 30, 504, 972)])
    assert 'keystroke "n" using command down' in script
    assert "set targetWin to front window" in script
    assert script.rstrip().endswith("end openWindow")


def test_custom_title_is_set_after_do_script():
    # `do script` overwrites Terminal's custom title with the command string on
    # macOS, so custom title must be (re-)set after do script runs, not before,
    # or the window ends up labeled with the command instead of the pane title.
    spec = _spec(Pane(title="1 SERVER", cmd="echo hi"))
    script = generate_layout_applescript(spec, [(0, 30, 504, 972)])
    assert script.index("do script cmd in targetWin") < script.index(
        "set custom title of targetWin to theTitle"
    )


NON_CUSTOM_TITLE_COMPONENTS = [
    "title displays device name",
    "title displays file name",
    "title displays shell path",
    "title displays window size",
]


def test_openwindow_handler_suppresses_the_five_non_custom_title_components():
    """Terminal's title bar concatenates every enabled component (device name,
    running command, window size, ...) onto the custom title, which is what
    leaked `arielfogel — ... — clear; — sleep 6 — 53×49` into a real take. Only
    `title displays custom title` may stay on; the other five must be forced off.
    """
    for prop in NON_CUSTOM_TITLE_COMPONENTS:
        assert f"set {prop} of selected tab of targetWin to false" in OPENWINDOW_HANDLER
    assert "set title displays custom title of selected tab of targetWin to true" in OPENWINDOW_HANDLER
    # Verify settings name is not present at all
    assert "title displays settings name" not in OPENWINDOW_HANDLER


def test_title_component_assignments_are_each_wrapped_in_their_own_try():
    """Matches the file's existing style for optional styling (current settings,
    font size): each property gets its own try/end try, so a single macOS
    version missing one property can't skip the rest of the block."""
    lines = [line.strip() for line in OPENWINDOW_HANDLER.splitlines()]
    props = ["title displays custom title", *NON_CUSTOM_TITLE_COMPONENTS]
    for prop in props:
        idx = next(
            i for i, line in enumerate(lines) if line.startswith(f"set {prop} of selected tab of targetWin")
        )
        # Nearest preceding unclosed `try` (walking back, an `end try` before a
        # `try` means we've left the enclosing block).
        opening_try = None
        for j in range(idx - 1, -1, -1):
            if lines[j] == "end try":
                break
            if lines[j] == "try":
                opening_try = j
                break
        assert opening_try is not None, f"{prop!r} assignment is not inside a try block"
        closing_end_try = next(
            k for k in range(idx + 1, len(lines)) if lines[k] == "end try"
        )
        assert closing_end_try > idx


def test_title_component_assignments_happen_before_do_script():
    """Unlike `custom title` (text), which `do script` clobbers and which must
    therefore be re-set afterward, the `title displays *` flags are untouched
    by `do script` — so they can (and should) be set once, early, right where
    the other optional window styling (current settings, font size) is set.
    Setting them before `do script` also means the title bar never shows the
    undecorated defaults, not even for one frame."""
    assert OPENWINDOW_HANDLER.index(
        "set title displays custom title of selected tab of targetWin to true"
    ) < OPENWINDOW_HANDLER.index("do script cmd in targetWin")


def test_generate_rejects_bounds_pane_mismatch():
    spec = _spec(Pane(title="a", cmd="echo hi"))
    with pytest.raises(ValueError, match="match pane count"):
        generate_layout_applescript(spec, [(0, 30, 1, 1), (0, 30, 2, 2)])


def test_generate_emits_final_retitling_pass():
    # The final re-titling pass wins the shell-startup race that clobbers the
    # first window's in-handler title set (see module docstring). Each window
    # variable must be re-titled once every window has been opened.
    spec = _spec(
        Pane(title="1 SERVER", cmd="echo a"),
        Pane(title="2 ADVERSARY", cmd="echo b"),
    )
    script = generate_layout_applescript(spec, [(0, 30, 504, 972), (504, 30, 1008, 972)])
    assert "set w1 to my openWindow(" in script
    assert "set w2 to my openWindow(" in script
    assert 'my setTitle(w1, "1 SERVER")' in script
    assert 'my setTitle(w2, "2 ADVERSARY")' in script


def test_retitling_pass_happens_after_all_windows_open():
    # The re-titling pass must only run after every openWindow call has
    # completed, not interleaved with them.
    spec = _spec(
        Pane(title="1 SERVER", cmd="echo a"),
        Pane(title="2 ADVERSARY", cmd="echo b"),
    )
    script = generate_layout_applescript(spec, [(0, 30, 504, 972), (504, 30, 1008, 972)])
    last_openwindow_call = script.rindex("my openWindow(")
    first_settitle_call = script.index("my setTitle(")
    assert last_openwindow_call < first_settitle_call


def _record_spec(**recording_kwargs):
    return Spec(
        recording=Recording(**recording_kwargs),
        layout=Layout(mode="columns"),
        panes=(
            Pane(title="1  SERVER", cmd="server.py", delay=4.0),
            Pane(title="2  VICTIM", cmd="victim.py"),
        ),
    )


RECORD_BOUNDS = [(0, 30, 756, 972), (756, 30, 1512, 972)]


def test_cleanup_script_lists_every_title():
    script = generate_cleanup_applescript(["1  SERVER", "2  VICTIM"])
    assert 'my closeDemoWindows({"1  SERVER", "2  VICTIM"})' in script
    assert script.endswith(CLOSEWINDOWS_HANDLER)


def test_cleanup_script_escapes_quotes_in_titles():
    assert '\\"q\\"' in generate_cleanup_applescript(['a "q" b'])


def test_cleanup_handler_does_not_iterate_while_closing():
    """Closing a window while still inside `repeat with <var> in windows` mutates
    the collection mid-iteration, which skips entries and leaves live windows
    behind — observed for real in a previous slice. The handler must instead scan
    read-only for one match, `exit repeat` out of the scan, and only `close` the
    victim once the scan loop has fully ended.

    This checks the structural property (close happens lexically after the scan
    loop's `end repeat`, not before it) rather than a superficial detail like the
    loop variable's name — a prior version of this test asserted the literal
    string "repeat with w in windows" was absent, which is vacuous: it passes for
    any handler that merely names its loop variable something other than `w`,
    even one that closes a window mid-scan under a different name.
    """
    lines = [line.strip() for line in CLOSEWINDOWS_HANDLER.splitlines()]

    # Locate the read-only scan loop: `repeat with <var> in windows`.
    scan_start = None
    loop_var = None
    for i, line in enumerate(lines):
        match = re.match(r"repeat with (\w+) in windows\b", line)
        if match:
            scan_start = i
            loop_var = match.group(1)
            break
    assert scan_start is not None, "expected a `repeat with <var> in windows` scan loop"

    # Find the `end repeat` that terminates the scan loop specifically, tracking
    # nesting depth so an unrelated `end repeat` (e.g. the outer retry loop's)
    # isn't mistaken for it.
    depth = 0
    scan_end = None
    for i in range(scan_start, len(lines)):
        line = lines[i]
        if line.startswith("repeat"):
            depth += 1
        elif line.startswith("end repeat"):
            depth -= 1
            if depth == 0:
                scan_end = i
                break
    assert scan_end is not None, "no matching `end repeat` found for the scan loop"

    # The scan loop must exit read-only on a match rather than acting on it.
    assert any("exit repeat" in line for line in lines[scan_start:scan_end])

    # There must be a `close` statement, and every one of them must happen after
    # the scan loop has fully ended — never lexically inside it.
    close_indices = [i for i, line in enumerate(lines) if line.startswith("close ")]
    assert close_indices, "expected a `close` statement in the handler"
    for close_index in close_indices:
        assert close_index > scan_end, (
            "`close` must come after the scan loop's `end repeat`, not inside the loop"
        )
        # What gets closed must not be the scan loop's own iteration variable —
        # the whole point is to close a saved-off reference after the scan ends,
        # not to act on the loop variable while (or as if) still iterating.
        closed_target = lines[close_index].split()[1]
        assert closed_target != loop_var


def test_record_script_settles_before_opening_anything():
    """ffmpeg needs a moment to start writing frames, or the first pane opening
    is missing from the take."""
    lines = generate_record_applescript(_record_spec(), RECORD_BOUNDS, "/tmp/rt").splitlines()
    assert lines[0] == "on run"
    assert lines[1] == "\tdelay 2"


def test_record_script_opens_each_pane_with_its_bounds():
    script = generate_record_applescript(_record_spec(), RECORD_BOUNDS, "/tmp/rt")
    assert 'set w1 to my openWindow(' in script
    assert "{0, 30, 756, 972}" in script
    assert "{756, 30, 1512, 972}" in script


def test_record_script_emits_a_pane_delay_after_its_window():
    script = generate_record_applescript(_record_spec(), RECORD_BOUNDS, "/tmp/rt")
    open_one = script.index("set w1 to")
    open_two = script.index("set w2 to")
    assert "\tdelay 4\n" in script[open_one:open_two]


def test_record_script_omits_a_zero_delay():
    script = generate_record_applescript(_record_spec(), RECORD_BOUNDS, "/tmp/rt")
    # pane 2 has delay 0.0; the only remaining delays are settle/titling/hold
    assert script.count("\tdelay 0\n") == 0


def test_record_script_bakes_the_runtime_dir_into_each_command():
    script = generate_record_applescript(_record_spec(), RECORD_BOUNDS, "/tmp/rt")
    assert script.count("DEMO_RUNTIME_DIR=/tmp/rt") == 2


def test_record_script_reasserts_titles_after_all_windows_open():
    """V2's two-phase titling: the first (cold) window loses its title to the
    zsh prompt escape unless it is re-set after everything has settled."""
    script = generate_record_applescript(_record_spec(), RECORD_BOUNDS, "/tmp/rt")
    assert 'my setTitle(w1, "1  SERVER")' in script
    assert script.index("set w2 to") < script.index("my setTitle(w1,")


def test_record_script_holds_before_returning():
    script = generate_record_applescript(_record_spec(hold=9.0), RECORD_BOUNDS, "/tmp/rt")
    run_body = script[: script.index("end run")]
    assert run_body.rstrip().endswith('return "record: opened 2 windows"')
    assert "\tdelay 9\n" in run_body


def test_record_script_reasserts_titles_after_the_hold():
    """A pane's own interactive shell clobbers its custom title the moment its
    command exits and zsh's prompt hook redraws the terminal title -- and
    `hold` exists precisely to keep a finished pane's last banner on screen,
    so this is the common case, not an edge case. The final frames (the ones
    a viewer looks at longest) must therefore get one more `setTitle` pass
    after the hold, immediately before `return`, regardless of when each
    pane's command exited."""
    script = generate_record_applescript(_record_spec(hold=9.0), RECORD_BOUNDS, "/tmp/rt")
    run_body = script[: script.index("end run")]
    hold_index = run_body.index("\tdelay 9\n")
    return_index = run_body.rindex('return "record: opened 2 windows"')
    final_w1 = run_body.rindex('my setTitle(w1, "1  SERVER")')
    final_w2 = run_body.rindex('my setTitle(w2, "2  VICTIM")')
    assert hold_index < final_w1 < return_index
    assert hold_index < final_w2 < return_index


def test_record_script_keeps_the_post_open_title_pass_alongside_the_post_hold_one():
    """The new post-hold re-assertion pass must be additional, not a
    replacement: the existing post-open pass (V2) still wins the cold-start
    race for the first pane opened in a run, which happens well before any
    command has had a chance to finish."""
    script = generate_record_applescript(_record_spec(hold=9.0), RECORD_BOUNDS, "/tmp/rt")
    run_body = script[: script.index("end run")]
    assert run_body.count('my setTitle(w1, "1  SERVER")') == 2
    assert run_body.count('my setTitle(w2, "2  VICTIM")') == 2
    hold_index = run_body.index("\tdelay 9\n")
    first_w1 = run_body.index('my setTitle(w1, "1  SERVER")')
    first_w2 = run_body.index('my setTitle(w2, "2  VICTIM")')
    assert first_w1 < hold_index
    assert first_w2 < hold_index


def test_record_script_reasserts_titles_before_return_even_with_no_hold():
    """hold=0 means no `delay` line is emitted for the hold at all (see
    test_record_script_omits_a_zero_delay), but a pane's command can still
    finish and clobber its title before the take ends -- so the final
    re-assertion pass must still be emitted, right before `return`, even when
    there is no hold delay line to anchor it to."""
    script = generate_record_applescript(_record_spec(hold=0.0), RECORD_BOUNDS, "/tmp/rt")
    run_body = script[: script.index("end run")]
    assert "\tdelay 0\n" not in run_body
    return_index = run_body.rindex('return "record: opened 2 windows"')
    final_w1 = run_body.rindex('my setTitle(w1, "1  SERVER")')
    final_w2 = run_body.rindex('my setTitle(w2, "2  VICTIM")')
    assert final_w1 < return_index
    assert final_w2 < return_index
    assert run_body.count('my setTitle(w1, "1  SERVER")') == 2
    assert run_body.count('my setTitle(w2, "2  VICTIM")') == 2


def test_record_script_keeps_openwindow_handler_last():
    """test_gen's V2 invariant: the file must still end with the window driver."""
    script = generate_record_applescript(_record_spec(), RECORD_BOUNDS, "/tmp/rt")
    assert script.rstrip().endswith("end openWindow")


def test_record_script_rejects_a_bounds_count_mismatch():
    with pytest.raises(ValueError, match="bounds count"):
        generate_record_applescript(_record_spec(), RECORD_BOUNDS[:1], "/tmp/rt")


def test_record_script_settles_after_final_titles_before_return_with_hold():
    """Without a settle delay after the final setTitle pass and before return,
    Terminal has not repainted the title bars before ffmpeg stops recording."""
    script = generate_record_applescript(_record_spec(hold=4.0), RECORD_BOUNDS, "/tmp/rt")
    run_body = script[: script.index("end run")]
    return_index = run_body.rindex('return "record: opened 2 windows"')
    final_w2 = run_body.rindex('my setTitle(w2, "2  VICTIM")')
    # There must be a delay line between the final setTitle and return
    settle_delay_line = "\tdelay 0.8"
    assert settle_delay_line in run_body[final_w2:return_index]
    # The delay must come after the final setTitle
    assert run_body.rindex(settle_delay_line) > final_w2
    # The delay must come before return
    assert run_body.rindex(settle_delay_line) < return_index


def test_record_script_settles_after_final_titles_before_return_without_hold():
    """Even with hold=0 (no delay line for hold), the final settle delay must
    still appear after the final setTitle and before return."""
    script = generate_record_applescript(_record_spec(hold=0.0), RECORD_BOUNDS, "/tmp/rt")
    run_body = script[: script.index("end run")]
    return_index = run_body.rindex('return "record: opened 2 windows"')
    final_w2 = run_body.rindex('my setTitle(w2, "2  VICTIM")')
    # There must be a delay line between the final setTitle and return
    settle_delay_line = "\tdelay 0.8"
    assert settle_delay_line in run_body[final_w2:return_index]
    # The delay must come after the final setTitle
    assert run_body.rindex(settle_delay_line) > final_w2
    # The delay must come before return
    assert run_body.rindex(settle_delay_line) < return_index

def test_non_finite_hold_is_rejected_by_validate_before_it_can_reach_generation():
    """Regression: TOML natively parses `inf`/`nan` as float literals, and a bare
    `< 0` check lets both through (inf < 0 is False; nan < 0 is also False). Left
    unchecked, generate_record_applescript would render `\\tdelay inf`, which
    osascript cannot execute. validate() is the single gate the CLI calls before
    generation, so it must be the one to reject this spec — closing the hazard
    here means it can never reach generate_record_applescript at all.
    """
    spec = _record_spec(hold=float("inf"))
    errors = validate(spec)
    assert any("hold" in e and "finite" in e for e in errors)


def test_backdrop_script_opens_a_full_screen_window_titled_with_the_backdrop_constant():
    script = generate_backdrop_applescript(1512, 982)
    assert "my openWindow(" in script
    assert f'"{BACKDROP_TITLE}"' in script
    assert "{0, 0, 1512, 982}" in script


def test_backdrop_script_reuses_the_openwindow_handler_rather_than_a_second_one():
    script = generate_backdrop_applescript(1512, 982)
    assert script.rstrip().endswith("end openWindow")
    # exactly one handler definition: the reused openWindow, not a bespoke one
    assert script.count("on openWindow(") == 1


def test_backdrop_command_leaves_a_blank_screen():
    # `clear` wipes any login banner, and the immediate foreground `sleep`
    # means a shell prompt is never drawn.
    script = generate_backdrop_applescript(1512, 982)
    assert "clear; sleep 86400" in script


def test_backdrop_script_reasserts_its_title_after_settling():
    """Confirmed on a real take: Terminal resyncs a window's custom title to
    whatever foreground process is running (here, the shell executing `clear;
    sleep 86400`) shortly after `do script` returns — the same race the module
    docstring describes for a cold shell's prompt escape, just triggered by
    Terminal's own process-title tracking instead. Without a Phase 2 re-assert,
    the backdrop is left titled "clear; sleep 86400" instead of BACKDROP_TITLE,
    so cleanup's closeDemoWindows never matches it and it leaks past the take.
    """
    script = generate_backdrop_applescript(1512, 982)
    assert "set w to my openWindow(" in script
    assert f'my setTitle(w, "{BACKDROP_TITLE}")' in script
    assert script.index("set w to my openWindow(") < script.index("my setTitle(w,")


def _gated_spec(**recording_kwargs):
    return Spec(
        recording=Recording(**recording_kwargs),
        layout=Layout(mode="columns"),
        panes=(
            Pane(title="1  SERVER", cmd="server.py", signals=("server_ready",)),
            Pane(title="2  VICTIM", cmd="victim.py", gate_on="server_ready"),
        ),
        verify=Verify(expect=("takeover.json",), timeout=45.0),
    )


def test_gate_wait_is_emitted_before_the_gated_window_opens():
    script = generate_record_applescript(_gated_spec(), RECORD_BOUNDS, "/tmp/rt")
    wait_at = script.index('waitForFile("/tmp/rt/server_ready"')
    assert script.index("set w1 to") < wait_at < script.index("set w2 to")


def test_gate_timeout_aborts_the_take_with_a_named_signal():
    """A silent continue would record a take that is missing its whole point."""
    script = generate_record_applescript(_gated_spec(gate_timeout=45.0), RECORD_BOUNDS, "/tmp/rt")
    assert (
        '\tif not my waitForFile("/tmp/rt/server_ready", 45) then '
        'error "pocumentary: timed out waiting for signal \'server_ready\'" number 9001'
        in script
    )


def test_ungated_pane_emits_no_wait():
    spec = _record_spec()  # neither pane has gate_on
    assert "waitForFile" not in generate_record_applescript(spec, RECORD_BOUNDS, "/tmp/rt")


def test_verify_expectations_are_awaited_before_the_hold():
    """Pacing, not verdict: the tape must not stop before the demo's result
    lands. The exit-code verdict is Python's job, so a timeout here does NOT
    error — it lets the take finish so the failure is on camera."""
    script = generate_record_applescript(_gated_spec(hold=9.0), RECORD_BOUNDS, "/tmp/rt")
    wait_at = script.index('my waitForFile("/tmp/rt/takeover.json", 45)')
    assert "error" not in script[wait_at : script.index("\n", wait_at)]
    assert wait_at < script.index("\tdelay 9\n")


def test_waitforfile_handler_is_included_once_when_used():
    script = generate_record_applescript(_gated_spec(), RECORD_BOUNDS, "/tmp/rt")
    assert script.count(WAITFORFILE_HANDLER) == 1


def test_openwindow_handler_is_still_last():
    script = generate_record_applescript(_gated_spec(), RECORD_BOUNDS, "/tmp/rt")
    assert script.rstrip().endswith("end openWindow")


def test_signal_names_are_escaped_in_the_generated_script():
    spec = Spec(
        recording=Recording(),
        layout=Layout(mode="columns"),
        panes=(
            Pane(title="a", cmd="x", signals=('we"ird',)),
            Pane(title="b", cmd="y", gate_on='we"ird'),
        ),
    )
    assert '\\"ird' in generate_record_applescript(spec, RECORD_BOUNDS, "/tmp/rt")


def test_fractional_gate_timeout_rounds_up_not_to_zero():
    """Fractional sub-second gate timeouts must round up to at least 1, not truncate to 0.
    The AppleScript handler loops `repeat with i from 1 to (N * 2)`, so N=0 runs zero
    iterations and returns false immediately, aborting the take even if the signal
    file already exists."""
    script = generate_record_applescript(_gated_spec(gate_timeout=0.5), RECORD_BOUNDS, "/tmp/rt")
    assert 'waitForFile("/tmp/rt/server_ready", 1)' in script
    assert 'waitForFile("/tmp/rt/server_ready", 0)' not in script


def test_fractional_verify_timeout_rounds_up_not_to_zero():
    """Fractional sub-second verify timeouts must also round up, not truncate to 0."""
    spec = Spec(
        recording=Recording(),
        layout=Layout(mode="columns"),
        panes=(
            Pane(title="1  SERVER", cmd="server.py", signals=("server_ready",)),
            Pane(title="2  VICTIM", cmd="victim.py", gate_on="server_ready"),
        ),
        verify=Verify(expect=("takeover.json",), timeout=0.5),
    )
    script = generate_record_applescript(spec, RECORD_BOUNDS, "/tmp/rt")
    assert 'waitForFile("/tmp/rt/takeover.json", 1)' in script
    assert 'waitForFile("/tmp/rt/takeover.json", 0)' not in script


def test_record_applescript_touches_a_marker_per_pane():
    from pocumentary.gen import generate_record_applescript
    from pocumentary.spec import parse
    from pocumentary.subtitles import marker_path

    spec = parse(
        '[layout]\nmode = "columns"\n'
        '[[pane]]\ntitle = "1  S"\ncmd = "echo a"\n'
        '[[pane]]\ntitle = "2  C"\ncmd = "echo b"\n'
    )
    bounds = [(0, 0, 100, 100), (100, 0, 200, 100)]
    script = generate_record_applescript(spec, bounds, "/tmp/rt")

    assert f'do shell script "touch " & quoted form of "{marker_path("/tmp/rt", 0)}"' in script
    assert f'do shell script "touch " & quoted form of "{marker_path("/tmp/rt", 1)}"' in script
    assert script.count('do shell script "touch "') == 2
