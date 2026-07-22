<p align="center">
  <img src="docs/pocumentary_logo.png" alt="PoCumentary" width="640">
</p>

<p align="center">
  <a href="https://pillar.security">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/pillar-logo-light.svg">
      <img src="docs/pillar-logo.svg" alt="Pillar Security" height="26">
    </picture>
  </a>
  <br>
  <sub>An open-source project from <a href="https://pillar.security">Pillar Security</a></sub>
</p>

# PoCumentary

**Turn a proof-of-concept into a narrated screen-recording — from one declarative spec, repeatably.**

PoCumentary is a spec-driven CLI for building multi-terminal demo recordings on
macOS. You describe a demo once in a `demo.toml` — the panes, the commands they
run, how they hand off to each other, and plain-language captions for each step
— and PoCumentary tiles the terminals, drives them in the right order, screen-
records the result, and burns event-anchored subtitles (or speaks them) onto the
take. The captions stay in sync because they anchor to demo **events**, not
wall-clock seconds, so you can re-word them without re-recording.

The command is `pocumentary` (or the short alias **`pocu`**).

```bash
pocu scaffold my-demo/                       # write a working starter demo.toml
pocu validate my-demo/demo.toml              # pure schema check, no screen
pocu dryrun   my-demo/demo.toml              # run the roles headless, assert success
pocu record   my-demo/demo.toml              # the on-screen take -> recording.mov (+ timeline)
pocu annotate my-demo/demo.toml recording.mov # burn [[annotation]] captions + [[overlay]] GIFs -> -captioned.mov
pocu narrate  my-demo/demo.toml recording.mov # speak the captions instead -> -narrated.mov
pocu explain                                 # print the full demo.toml schema reference
```
## Worked example

[`examples/langroid-cypher-rce/`](examples/langroid-cypher-rce/) is a full demo:
a three-terminal reproduction of a real, published critical CVE
([CVE-2026-55615](https://github.com/advisories/GHSA-2pq5-3q89-j7cc), CVSS 9.2) —
a Cypher injection in langroid's `Neo4jChatAgent` that ends in remote code
execution (a real `popcalc`). Its caption/narration track walks the four steps of
the attack and can be burned in as subtitles or spoken as TTS narration; it runs
on plain `python3` with no extra dependencies. See its README for more information about the vulnerability, killchain diagram, and run commands.
`examples/gated-demo.toml` is a smaller two-pane handshake if you just want to
see the mechanics.

[langroid-cypher-rce-demo.webm](https://github.com/user-attachments/assets/0cb21bbc-2fc2-407b-84d1-c9dca2e3fcb5)


## Why

In an age where we ship more findings than any of us can keep up with, the bug
is only half the battle — someone still has to *believe* you. A wall of text and
a stack trace don't land; a clean, narrated repro does. In a world drowning in
findings, you need the right tools by your side. Enter PoCumentary.

Recording a clean multi-actor PoC by hand is fiddly and fragile: windows must be
placed and titled, actors must start in the right order, the capture must be
cropped to just the demo, and captions drift the moment a step takes longer than
last take. PoCumentary makes the whole thing declarative and repeatable, and
keeps the timing-sensitive parts (layout math, gating, crop, captioning) pure
and unit-tested so a demo behaves the same every run.

## Install

Requires Python ≥ 3.11 and [`uv`](https://docs.astral.sh/uv/). The core has
**no runtime dependencies** (stdlib only); `ffmpeg` is shelled out.

```bash
git clone <this-repo> && cd pocumentary
uv run pocu --help          # uv resolves the project and both entry points

# On-screen recording (`record`) needs macOS + ffmpeg + Screen Recording
# permission for your terminal. Everything else runs anywhere. (`narrate`
# also needs ffprobe, which ships with ffmpeg.)
brew install ffmpeg

# Optional: spoken narration (`narrate`) uses ElevenLabs (cloud, high quality).
uv pip install 'pocumentary[tts]'

# Optional fallback: on-device TTS used automatically when no API key is set
# (Apple Silicon, ~1.7 GB model on first run).
uv pip install 'pocumentary[tts-local]'
```

### Narration credentials (ElevenLabs)

`narrate` resolves an ElevenLabs API key at run time — it never stores one.
It looks in this order: the `ELEVENLABS_API_KEY` environment variable, then a
`.env` beside the `demo.toml`, then a `.env` in the current directory. **If no
key is found it falls back to the on-device engine automatically** (install
`pocumentary[tts-local]` for that path).

```bash
# Global (every `pocu narrate`, anywhere) — add to your shell profile:
echo 'export ELEVENLABS_API_KEY=sk_your_key_here' >> ~/.zshrc && source ~/.zshrc

# Per-project — drop a git-ignored .env beside the demo (keeps it out of history):
echo 'ELEVENLABS_API_KEY=sk_your_key_here' > my-demo/.env
```

A globally-installed `pocu` (see below) runs in its own venv but still inherits
your shell environment, so the shell-profile export reaches it with no extra
setup. Pick a voice/model in the demo's `[tts]` block (see `pocu explain`).

### Install globally (run `pocu` anywhere)

Use uv's tool installer (the pipx equivalent) to put both `pocu` and
`pocumentary` on your PATH, in an isolated environment:

```bash
# From a clone of this repo. --editable makes the global command track your
# working copy, so edits and `git pull`s take effect with no reinstall.
uv tool install --editable .

# Include spoken narration in the global tool as well (ElevenLabs, + on-device
# fallback). The API key comes from your shell profile — see "Narration
# credentials" above; the global tool inherits it.
uv tool install --editable . --with elevenlabs --with mlx-audio

# Or install straight from the repo, no clone needed:
uv tool install git+ssh://git@github.com/pillar-labs/pocumentary

pocu --help                 # now works from any directory
```

The executables land in `~/.local/bin` (run `uv tool update-shell` once if that
isn't on your PATH). Manage the install with `uv tool upgrade pocumentary` and
`uv tool uninstall pocumentary`. Note: an `--editable` install points at the
directory you ran it from — moving or deleting that clone breaks the command.

## The workflow

PoCumentary is built around a cheap inner loop and one expensive step:

1. **`scaffold`** writes a runnable starter `demo.toml` + role stubs.
2. **`validate`** is a pure schema check — no screen, instant.
3. **`dryrun`** runs the roles headless and flat-out, sequenced by their gates,
   and exits non-zero unless the demo's `[verify]` predicate holds. This is how
   you iterate without paying for a screen take.
4. **`record`** is the one expensive step: tile the terminals, screen-record with
   ffmpeg (cropped to just the panes), and write `recording.mov` plus a
   `recording.mov.timeline.json` sidecar mapping each event to its video offset.
5. **`annotate`** / **`narrate`** consume that timeline to burn captions (and any
   `[[overlay]]` GIFs) or mix spoken audio onto the take — re-runnable, so
   re-wording never needs a new take.

## The `demo.toml`

Run `pocu explain` for the authoritative, always-current reference. In brief:

```toml
[recording]                 # all optional
fps = 30
crop = "auto"               # "auto" | "none" | "W:H:X:Y" (pixels)
step_delay = 2.0            # readable per-step pacing, baked in as $DEMO_STEP_DELAY
hold = 6.0                  # keep rolling this long after the last pane finishes

[layout]
mode = "columns"            # "columns" | "rows" | "grid"

[verify]                    # optional success predicate
expect = ["done"]           # handshake files that must exist when the demo ends

[[pane]]                    # one or more
title = "1 SERVER"
cmd = "python server.py"    # paths resolve against the demo.toml's directory
signals = ["server_ready"]  # handshake files this pane emits (under $DEMO_RUNTIME_DIR)

[[pane]]
title = "2 CLIENT"
cmd = "python client.py"
gate_on = "server_ready"    # do not start until an earlier pane emits this signal

[[annotation]]              # optional caption, zero or more
on = "server_ready"         # WHEN it appears: "start" | a signal name | "pane:<title>"
text = "The server is up and listening."
duration = 4.0

[[overlay]]                 # optional image/GIF easter egg, zero or more
on = "takeover"             # same anchors as [[annotation]]
gif = "boom.gif"            # local path OR an http(s) URL fetched at annotate time
duration = 3.0              # seconds it pops on screen, then off
scale = 0.4                 # width as a fraction of the frame
position = "center"         # center | top-left | top-right | bottom-left | bottom-right

[tts]                       # optional, for `narrate` (ElevenLabs)
voice_id = "ySr9tfpEeN2Sp5JTEEW1"
model_id = "eleven_multilingual_v2"
speed = 1.0                 # ElevenLabs voice-setting rate (~0.7–1.2)
```

**Events and timing.** Every pane's command sees `$DEMO_RUNTIME_DIR` (a shared
handshake directory) and `$DEMO_STEP_DELAY` (the pacing beat). A pane emits a
signal by touching `$DEMO_RUNTIME_DIR/<name>`; another pane can `gate_on` it, and
a caption can anchor `on` it. The recorder's timeline captures the offset of
`start`, each `pane:<title>` opening, and each signal — those are the anchors
`annotate`/`narrate` line captions up to.

**Authoring captions.** Write one short, complete, grammatical sentence per step.
`validate` warns when a line looks too long to speak within its `duration`, and
`narrate` errors if a synthesized clip would overrun the gap to the next event.

## Driving PoCumentary with an AI agent

The repo ships a [Claude Code](https://claude.com/claude-code) skill —
[`.claude/skills/using-pocumentary/SKILL.md`](.claude/skills/using-pocumentary/SKILL.md) —
that teaches an agent the workflow: iterate headlessly with `dryrun`, spend the
one expensive `record`, then re-run `annotate`/`narrate`, plus the sharp edges
(the timeline-sidecar contract, macOS/permission requirements, safety).

- **In this repo:** nothing to install. Claude Code auto-discovers project skills
  under `.claude/skills/`, so an agent working here loads it when it's relevant;
  you can also invoke it explicitly with `/using-pocumentary`.
- **Anywhere (a global install of `pocu`, driving demos in other repos):** copy
  the skill into your personal skills directory so it travels with you:

  ```bash
  cp -r .claude/skills/using-pocumentary ~/.claude/skills/
  ```

It's a reference skill — reading it (or `pocu explain`) is meant to replace
digging through `src/` to figure out how to drive the tool.

## Architecture

PoCumentary keeps a strict **pure/effect split**. The pure modules (`spec`,
`layout`, `crop`, `cmd`, `gen`, `ffmpeg`, `gates`, `subtitles`, `narration`,
`scaffold`, `explain`) do all the reasoning — schema parsing, geometry and crop
math, AppleScript generation, gate-wiring checks, the event→subtitle transform,
the ffmpeg argv — with no I/O, so they are unit-tested without a screen. The
effect edges (`detect`, `driver`, `record`, `postprod`, `synth`, `cli`) are thin
wrappers that actually run osascript, ffmpeg, and the TTS engine. Spoken
narration prefers ElevenLabs (cloud, opt-in `pocumentary[tts]` extra) and falls
back to an on-device engine (`pocumentary[tts-local]`) with a pinned seed when
no API key is set — the key is resolved from the environment or a project `.env`
and never stored by the tool.

## Tests

```bash
uv run pytest -q          # the full suite (pure core is exhaustively covered)
```

## Running demos safely

**A `demo.toml` is code.** `record` and `dryrun` execute each pane's `cmd` on
your machine, as you, with your privileges. Running whatever the spec says to run
is by design — PoCumentary is a PoC recorder, and a PoC *is* an exploit (the
worked example ends in a real `popcalc`). That makes running code responsibly
your call: only run demos you wrote or have read, and isolate anything untrusted
(a container, a throwaway VM) as you see fit. You are responsible for what you
choose to run.

## Status & limits

- `record` is **macOS-only** (Terminal.app + AVFoundation). It targets the
  **main display**; the demo tiles on one screen.
- `target = "ssh:<host>"` (remote panes) is parsed but reserved for a future
  release; only `local` runs today.
- Authorized use only. PoCumentary records whatever you tell it to run.