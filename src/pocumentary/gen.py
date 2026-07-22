"""Pure AppleScript generation (N7) for layout preview.

The openWindow handler is lifted verbatim from
docs/reference/fastmcp-cand003/record_cand003.applescript — the ⌘N-first pattern that
creates the window frontmost, THEN titles/styles/positions it, THEN runs the command,
which is the fix for the `front window` race.

Deliberate deviation from the reference: `custom title` is set AFTER `do script`
(rather than before), because on macOS `do script` overwrites the window's custom
title with the command string — setting it beforehand gets clobbered.

Titling is two-phase. Phase 1 (in-handler): each `openWindow` call sets the custom
title itself right after `do script`, after a short delay — this makes the label
appear immediately in the common case. Phase 2 (final pass): after every window has
been opened, `run` waits out a longer settle delay and re-asserts every title via
`setTitle`. Phase 1 alone loses a race for the first window opened in a run: Terminal
is cold, so that shell starts slowly and its zsh prompt emits its own title-setting
escape sequence AFTER our phase-1 set, clobbering it (later windows, opened once
Terminal is warm, settle in time and are unaffected). Phase 2 closes that race
deterministically instead of just narrowing it with a longer fixed delay.

generate_record_applescript's titling is actually three-phase: on top of
Phases 1 and 2 above, it runs a Phase 3 that re-asserts every pane's title one
more time after `hold`, immediately before `return`. Phases 1 and 2 only guard
the moment each window opens; they say nothing about what happens once a
pane's own command finishes. When that happens mid-take, the interactive
shell it drops back to prints its own prompt, and zsh's prompt hook emits a
title-setting escape sequence that overwrites the custom title Phase 2 set,
for the rest of the take. This is the common case, not an edge case: demo
roles normally finish and then `hold` keeps the last banner on screen
specifically so a viewer can read it, so without Phase 3 the frames looked at
longest are exactly the ones most likely to be mislabeled. Phase 3 does not,
and cannot, stop a title from flipping mid-take the instant a command exits
and before Phase 3 runs -- doing that would mean suppressing the shell's own
title escape (e.g. patching the zsh prompt hook), which is out of scope here.

Title bars are also explicitly stripped of every component but the custom title
(device name, running command/shell path, settings name, file name, window size)
right after the window is targeted -- Terminal's title bar otherwise concatenates
every enabled component onto whatever `custom title` says, which is how a real
take leaked the username, the running shell command, and the window dimensions
onto the recording. Unlike `custom title` (text), these `title displays *` flags
are never touched by `do script`, so they are set once, early, rather than
re-asserted after it.
"""
from __future__ import annotations

import math

from pocumentary.cmd import build_command, pane_env
from pocumentary.gates import resolve_steps, signal_path
from pocumentary.layout import Bounds
from pocumentary.spec import Spec
from pocumentary.subtitles import marker_path

OPENWINDOW_HANDLER = """
on openWindow(cmd, theTitle, theBounds)
\ttell application "Terminal" to activate
\tdelay 0.3
\ttell application "System Events" to keystroke "n" using command down
\tdelay 0.7
\ttell application "Terminal"
\t\tset targetWin to front window
\t\ttry
\t\t\tset current settings of selected tab of targetWin to settings set "Clear Dark"
\t\tend try
\t\ttry
\t\t\tset font size of selected tab of targetWin to 14
\t\tend try
\t\ttry
\t\t\tset title displays custom title of selected tab of targetWin to true
\t\tend try
\t\ttry
\t\t\tset title displays device name of selected tab of targetWin to false
\t\tend try
\t\ttry
\t\t\tset title displays file name of selected tab of targetWin to false
\t\tend try
\t\ttry
\t\t\tset title displays shell path of selected tab of targetWin to false
\t\tend try
\t\ttry
\t\t\tset title displays window size of selected tab of targetWin to false
\t\tend try
\t\tset bounds of targetWin to theBounds
\t\tdo script cmd in targetWin
\t\tdelay 0.3
\t\ttry
\t\t\tset custom title of targetWin to theTitle
\t\tend try
\t\tset bounds of targetWin to theBounds
\tend tell
\treturn targetWin
end openWindow
""".strip("\n")

SETTITLE_HANDLER = """
on setTitle(theWin, theTitle)
\ttry
\t\ttell application "Terminal" to set custom title of theWin to theTitle
\tend try
end setTitle
""".strip("\n")

# Lifted verbatim from docs/reference/fastmcp-cand003/record_cand003.applescript.
# Polls twice a second; returns false rather than erroring so the caller decides
# whether a timeout is fatal.
WAITFORFILE_HANDLER = """
on waitForFile(filePath, maxSeconds)
\trepeat with i from 1 to (maxSeconds * 2)
\t\ttry
\t\t\tdo shell script "test -e " & quoted form of filePath
\t\t\treturn true
\t\ton error
\t\t\tdelay 0.5
\t\tend try
\tend repeat
\treturn false
end waitForFile
""".strip("\n")


def escape_applescript_string(s: str) -> str:
    """Escape a Python string for embedding inside an AppleScript double-quoted literal."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def generate_layout_applescript(spec: Spec, bounds: list[Bounds]) -> str:
    if len(bounds) != len(spec.panes):
        raise ValueError("bounds count must match pane count")

    lines = ["on run"]
    titles = []
    for i, (pane, (x1, y1, x2, y2)) in enumerate(zip(spec.panes, bounds), start=1):
        cmd = build_command(pane.cmd, pane.env, pane.cwd)
        escaped_title = escape_applescript_string(pane.title)
        titles.append(escaped_title)
        lines.append(
            f'\tset w{i} to my openWindow("{escape_applescript_string(cmd)}", '
            f'"{escaped_title}", '
            f"{{{x1}, {y1}, {x2}, {y2}}})"
        )
    lines.append("\tdelay 0.8")
    for i, escaped_title in enumerate(titles, start=1):
        lines.append(f'\tmy setTitle(w{i}, "{escaped_title}")')
    lines.append(f'\treturn "layout: opened {len(spec.panes)} windows"')
    lines.append("end run")
    lines.append("")
    lines.append(SETTITLE_HANDLER)
    lines.append("")
    lines.append(OPENWINDOW_HANDLER)
    return "\n".join(lines)


SETTLE_DELAY_S = 2.0  # let ffmpeg start writing frames before the first window appears
TITLE_SETTLE_DELAY_S = 0.8  # V2: wait out the zsh prompt escape before re-titling

BACKDROP_TITLE = "pocumentary backdrop"
# `sleep` runs in the foreground right after `clear`, so no shell prompt is ever
# drawn — a bare login shell would print a "Last login:" banner that would show
# through the seams between panes.
BACKDROP_CMD = "sleep 86400"

CLOSEWINDOWS_HANDLER = """
on closeDemoWindows(theTitles)
\ttell application "Terminal"
\t\trepeat
\t\t\tset victim to missing value
\t\t\trepeat with eachWindow in windows
\t\t\t\ttry
\t\t\t\t\tif theTitles contains (custom title of eachWindow) then
\t\t\t\t\t\tset victim to eachWindow
\t\t\t\t\t\texit repeat
\t\t\t\t\tend if
\t\t\t\tend try
\t\t\tend repeat
\t\t\tif victim is missing value then exit repeat
\t\t\tclose victim saving no
\t\t\tdelay 0.2
\t\tend repeat
\tend tell
end closeDemoWindows
""".strip("\n")


def _applescript_list(items: list[str]) -> str:
    """Render Python strings as an AppleScript list literal."""
    return "{" + ", ".join(f'"{escape_applescript_string(i)}"' for i in items) + "}"


def _delay_line(seconds: float) -> str:
    return f"\tdelay {seconds:g}"


def generate_cleanup_applescript(titles: list[str]) -> str:
    """A standalone script that closes any demo windows matching these titles.

    Run before a take (clear leftovers) and after one (tidy up, off-camera).
    """
    return "\n".join(
        [
            "on run",
            f"\tmy closeDemoWindows({_applescript_list(titles)})",
            f'\treturn "cleanup: done"',
            "end run",
            "",
            CLOSEWINDOWS_HANDLER,
        ]
    )


def generate_backdrop_applescript(width_pt: int, height_pt: int) -> str:
    """A standalone script that opens a full-screen, blank Terminal window.

    Run before ffmpeg starts (and before any pane opens), so the only thing
    ever behind or between the staggered panes is this backdrop, never the
    operator's own desktop/session content. Reuses `openWindow` rather than a
    second window-opening code path — same ⌘N-first creation, same in-handler
    titling.

    Titling is still two-phase, same as generate_record_applescript, even
    though the backdrop's command never draws a shell prompt: confirmed on a
    real take, Terminal resyncs a window's custom title to whatever foreground
    process is running shortly after `do script` returns, which is the same
    race the module docstring describes for a cold shell's prompt escape, just
    triggered by Terminal's own process-title tracking instead of zsh. Skipping
    the re-assert left the backdrop titled "clear; sleep 86400" instead of
    BACKDROP_TITLE, so cleanup's closeDemoWindows never matched it and it
    leaked past the take.

    Bounds are the full screen, {0, 0, width_pt, height_pt}: its title bar and
    bottom edge then fall outside the crop region (the union of pane bounds),
    so they never appear in the recording either.
    """
    command = build_command(BACKDROP_CMD)
    escaped_title = escape_applescript_string(BACKDROP_TITLE)
    return "\n".join(
        [
            "on run",
            f'\tset w to my openWindow("{escape_applescript_string(command)}", '
            f'"{escaped_title}", '
            f"{{0, 0, {width_pt}, {height_pt}}})",
            _delay_line(TITLE_SETTLE_DELAY_S),
            f'\tmy setTitle(w, "{escaped_title}")',
            '\treturn "backdrop: opened"',
            "end run",
            "",
            SETTITLE_HANDLER,
            "",
            OPENWINDOW_HANDLER,
        ]
    )


def generate_record_applescript(spec: Spec, bounds: list[Bounds], runtime_dir: str) -> str:
    """The on-screen half of a take: open every pane, pace it, hold, return.

    ffmpeg is NOT started here — Python owns the recorder so its failures reach
    the exit code. Window cleanup is also separate, so it never lands on camera.

    Two kinds of wait are emitted, and they are deliberately different:
      * a GATE wait errors on timeout — the next pane depends on it, so
        continuing would record a meaningless take;
      * a VERIFY wait ignores its result — it exists only to stop the tape from
        cutting before the demo's outcome lands. The pass/fail verdict is
        Python's, in pocumentary.verify.
    """
    if len(bounds) != len(spec.panes):
        raise ValueError("bounds count must match pane count")

    steps = resolve_steps(spec)
    gate_timeout = math.ceil(spec.recording.gate_timeout)

    lines = ["on run", _delay_line(SETTLE_DELAY_S)]
    titles: list[str] = []

    for step, pane, (x1, y1, x2, y2) in zip(steps, spec.panes, bounds):
        if step.wait_for:
            path = escape_applescript_string(signal_path(runtime_dir, step.wait_for))
            signal = escape_applescript_string(step.wait_for)
            lines.append(
                f'\tif not my waitForFile("{path}", {gate_timeout}) then '
                f"error \"pocumentary: timed out waiting for signal '{signal}'\" number 9001"
            )

        command = build_command(
            pane.cmd, pane_env(pane, runtime_dir, spec.recording.step_delay), pane.cwd
        )
        escaped_title = escape_applescript_string(pane.title)
        titles.append(escaped_title)
        lines.append(
            f'\tset w{step.index + 1} to my openWindow('
            f'"{escape_applescript_string(command)}", '
            f'"{escaped_title}", '
            f"{{{x1}, {y1}, {x2}, {y2}}})"
        )
        marker = escape_applescript_string(marker_path(runtime_dir, step.index))
        lines.append(f'\tdo shell script "touch " & quoted form of "{marker}"')
        if step.delay > 0:
            lines.append(_delay_line(step.delay))

    lines.append(_delay_line(TITLE_SETTLE_DELAY_S))
    for i, escaped_title in enumerate(titles, start=1):
        lines.append(f'\tmy setTitle(w{i}, "{escaped_title}")')

    for name in spec.verify.expect:
        path = escape_applescript_string(signal_path(runtime_dir, name))
        lines.append(f'\tmy waitForFile("{path}", {math.ceil(spec.verify.timeout)})')

    if spec.recording.hold > 0:
        lines.append(_delay_line(spec.recording.hold))

    # Phase 3 (final re-assertion, after the hold): re-run setTitle for every
    # pane one more time, right before `return`. Fixes: a pane's command
    # finishing mid-take drops it back to an interactive shell prompt, whose
    # zsh prompt hook emits its own title escape and clobbers the custom
    # title the Phase 2 pass above set -- and `hold` exists precisely to keep
    # a just-finished pane's last banner on screen, so this is the common
    # case, not a rare one. This pass guarantees the closing, longest-held
    # frames are always labeled correctly, no matter when each pane's command
    # exited. Does NOT fix: a title flipping mid-take, the moment some
    # command exits and before this pass runs -- that would require
    # suppressing the shell's own title escape sequence, which is out of
    # scope (see module docstring).
    for i, escaped_title in enumerate(titles, start=1):
        lines.append(f'\tmy setTitle(w{i}, "{escaped_title}")')

    # Settle delay after final title pass: without this, `return` fires
    # immediately and Python stops ffmpeg before Terminal has repainted
    # the title bars, leaving the corrected labels off the recording.
    lines.append(_delay_line(TITLE_SETTLE_DELAY_S))

    lines.append(f'\treturn "record: opened {len(spec.panes)} windows"')
    lines.append("end run")
    lines.append("")
    lines.append(SETTITLE_HANDLER)
    if "my waitForFile(" in "\n".join(lines):
        lines.append("")
        lines.append(WAITFORFILE_HANDLER)
    lines.append("")
    lines.append(OPENWINDOW_HANDLER)
    return "\n".join(lines)
