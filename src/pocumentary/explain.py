"""Agent-consumable schema reference (N16, R7.1). Pure: returns text, no I/O."""
from __future__ import annotations

_REFERENCE = """\
pocumentary demo.toml — schema reference
====================================

A demo.toml describes a multi-pane terminal demo. Build one with this loop:

  pocumentary scaffold my-demo/     # write a working starter (this schema, filled in)
  pocumentary explain               # print this reference
  pocumentary validate my-demo/demo.toml   # pure schema check, no screen
  pocumentary dryrun   my-demo/demo.toml   # run the roles headless, assert success
  pocumentary record   my-demo/demo.toml   # the full on-screen take (macOS only)
  pocumentary annotate my-demo/demo.toml recording.mov  # burn [[annotation]] captions onto a take
  pocumentary narrate  my-demo/demo.toml recording.mov  # speak [[annotation]] lines, mix onto a take
  (pocu is a shorter alias for pocumentary — e.g. `pocu record ...`)

Paths in a pane's `cmd`/`cwd` are resolved against the demo.toml's own
directory, so a demo runs the same from anywhere.

[recording]                     (all keys optional)
  fps          int    = 30      frames per second; must be positive
  out          str    = "recording-{stamp}.mov"
                                output filename; {stamp} → a timestamp. Must be
                                a relative path with no ".." segments.
  crop         str    = "auto"  "auto" | "none" | "W:H:X:Y" (W, H, X, Y are
                                unsigned integers; in pixels)
  hold         float  = 6.0     seconds to keep recording after the last pane
                                finishes; must be finite and >= 0
  step_delay   float  = 0.0     baked into every pane as $DEMO_STEP_DELAY for
                                human-readable pacing; forced to 0 in dryrun.
                                Must be finite and >= 0
  keep         int    = 0       old takes to retain when pruning; 0 = keep all;
                                must be >= 0
  gate_timeout float  = 60.0    seconds to wait for any one gate signal; must be
                                finite and positive

[layout]                        (required)
  mode         str              "columns" | "rows" | "grid"

[verify]                        (optional — the success predicate)
  expect       list[str] = []   handshake filenames (relative to the runtime
                                dir) that must exist when the demo ends; each
                                must be non-empty. dryrun/record exit non-zero
                                if any is missing.
  timeout      float  = 60.0    seconds to wait for expectations; finite, > 0

[[pane]]                        (one or more required)
  title        str              window title; required, unique across panes
  cmd          str              shell command run in the pane; required
  env          table = {}       extra environment variables for this pane
  cwd          str = None       working directory; relative paths resolve
                                against the demo.toml's directory
  delay        float = 0.0      seconds to wait after opening this pane before
                                the next; finite and >= 0
  signals      list[str] = []   handshake files this pane emits (touched under
                                $DEMO_RUNTIME_DIR by the role script); signal
                                names must be unique across all panes
  gate_on      str = None      a signal this pane waits for before starting.
                                Must be emitted by an earlier pane (no deadlock).
  target       str  = "local"   "local" | "ssh:<host>". Remote is reserved for a
                                future release; only "local" runs today.

Every pane's command sees $DEMO_RUNTIME_DIR (the handshake directory) and
$DEMO_STEP_DELAY (the pacing beat) in its environment.

[[annotation]]                  (optional, zero or more — V6 subtitles)
  on           str              when the caption appears: "start" | a pane's
                                signal name | "pane:<title>"
  text         str              the caption text; must be non-empty
  duration     float = 4.0      seconds the caption stays on screen; finite, > 0

[[overlay]]                     (optional, zero or more — V8 image/GIF easter egg)
  on           str              when it pops on: "start" | a signal | "pane:<title>"
  gif          str              a local path (resolved vs the demo.toml dir) or an
                                http(s) URL fetched at annotate time
  duration     float = 3.0      seconds it stays on screen, then off; finite, > 0
  scale        float = 0.4      width as a fraction of the frame; 0 < scale <= 1
  position     str   = "center" center | top-left | top-right | bottom-left |
                                bottom-right
`pocumentary annotate` burns any [[overlay]] GIFs (looping, time-gated) on top of
the captions — e.g. a mind-blown GIF anchored to the "takeover" signal.

[tts]                           (optional — V7 spoken narration, ElevenLabs)
  voice_id     str    = "ySr9tfpEeN2Sp5JTEEW1"   ElevenLabs voice id
  model_id     str    = "eleven_multilingual_v2"  ElevenLabs model id
  speed        float  = 1.0    speaking-rate multiplier (~0.7–1.2); finite, > 0
  seed         int    = 42     synthesis seed; best-effort reproducibility (>= 0)

`pocumentary narrate` speaks each [[annotation]]'s `text` with ElevenLabs and mixes
the clips onto the recording at the same event offsets the captions use. It needs
the SDK (pip install 'pocumentary[tts]') and an API key in $ELEVENLABS_API_KEY or a
`.env` beside the demo.toml (ELEVENLABS_API_KEY=...).

Narration authoring: write ONE short, complete, grammatical sentence per step —
full sentences read far more naturally than fragments ("The server is up." not
"Server up"). Keep each line within its step's `duration` (roughly duration x 11
characters); `validate` warns when a line looks too long, and `narrate` errors if
a synthesized clip would overrun the gap to the next event.

Reserved (parsed and preserved, not yet acted on): target = "ssh:<host>".
This is for a future release.
"""


def explain() -> str:
    """Return the full demo.toml schema reference, ready to print."""
    return _REFERENCE
