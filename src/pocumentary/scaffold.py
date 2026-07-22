"""Starter-demo generator (N15, R7.1). Pure: returns {path: contents}, no I/O.

The starter is a two-pane gated handshake mirroring examples/gated-demo.toml:
a server that signals readiness and a client that gates on it and writes the
file the [verify] block asserts. It validates and passes `dryrun` as emitted,
so a coding agent can scaffold, confirm the loop is green, then edit the roles
for its own demo. The CLI (an edge) writes these strings to disk.
"""
from __future__ import annotations

_SERVER_SH = """\
#!/bin/sh
# The "server" role. Does some setup, then signals readiness by touching a file
# in $DEMO_RUNTIME_DIR. The client pane waits (gate_on) for exactly this signal.
set -eu
echo "=== SERVER ==="
sleep "${DEMO_STEP_DELAY:-0}"
echo "  >> starting up"
: > "$DEMO_RUNTIME_DIR/server_ready"
echo "  ** signalled: server_ready"
# Hold the final frame during `record`; dryrun tears this down as soon as the
# [verify] file appears, so the sleep never slows the headless loop.
sleep 30
"""

_CLIENT_SH = r"""#!/bin/sh
# The "client" role. Runs only after the server signals (see gate_on), then
# writes the file the [verify] block asserts on.
set -eu
echo "=== CLIENT ==="
sleep "${DEMO_STEP_DELAY:-0}"
echo "  >> connecting to the server"
printf '{"result": "ok"}\n' > "$DEMO_RUNTIME_DIR/handoff.json"
echo "  ** wrote handoff.json"
sleep 30
"""


def _demo_toml(name: str) -> str:
    return f"""\
# Starter demo scaffolded by `pocumentary scaffold`. A two-pane gated handshake — the
# smallest complete demo: gating, pacing, cropping, and verification.
#
#   Cheap loop:     uv run pocumentary dryrun demo.toml
#   Expensive take: uv run pocumentary record demo.toml
#
# The CLIENT pane will not start until the SERVER writes the `server_ready`
# handshake, so a recording never shows the client racing a server that is
# not up yet. Run `pocumentary explain` for the full schema reference.
[recording]
fps = 30
out = "{name}-{{stamp}}.mov"
crop = "auto"
step_delay = 1.0
gate_timeout = 30.0
hold = 4.0
keep = 3

[layout]
mode = "columns"

[verify]
expect = ["handoff.json"]
timeout = 30

[[pane]]
title = "1  SERVER"
cmd = "sh roles/server.sh"
signals = ["server_ready"]

[[pane]]
title = "2  CLIENT"
cmd = "sh roles/client.sh"
gate_on = "server_ready"

# Narration (V6 captions + V7 speech). `on` anchors each line to a demo EVENT —
# recording start, a pane opening, or a signal firing — so timing never needs
# hand-tuning. Write ONE short, complete sentence per step. Run the take, then:
#   uv run pocumentary annotate demo.toml <recording>.mov  ->  <recording>-captioned.mov
#   uv run pocumentary narrate  demo.toml <recording>.mov  ->  <recording>-narrated.mov  (needs: pip install 'pocumentary[tts]')
[[annotation]]
on = "start"
text = "This demo runs a server and a client."
duration = 4.0

[[annotation]]
on = "server_ready"
text = "The server is up. The client can connect now."
duration = 5.0

# Easter egg (V8): pop an image/GIF on screen at an event, then off. `annotate`
# burns it on top of the captions. `gif` is a local path or an http(s) URL.
# [[overlay]]
# on = "server_ready"
# gif = "https://media.giphy.com/media/lXu72d4iKwqek/giphy.gif"
# duration = 3.0
# scale = 0.4          # width as a fraction of the frame
# position = "center"  # center | top-left | top-right | bottom-left | bottom-right

# Spoken narration (V7, ElevenLabs). Defaults shown; the whole block is optional.
# `narrate` reads the API key from $ELEVENLABS_API_KEY or a .env beside this file.
[tts]
voice_id = "ySr9tfpEeN2Sp5JTEEW1"
model_id = "eleven_multilingual_v2"
speed = 1.0
seed = 42
"""


def scaffold_files(name: str = "demo") -> dict[str, str]:
    """Return {relative_path: contents} for a working starter demo.

    `name` is interpolated into the recording's output filename. The result
    validates and passes `dryrun` with no edits.
    """
    return {
        "demo.toml": _demo_toml(name),
        "roles/server.sh": _SERVER_SH,
        "roles/client.sh": _CLIENT_SH,
    }
