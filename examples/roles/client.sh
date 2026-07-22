#!/bin/sh
# Stands in for the acting role. Runs only once the server has signalled, then
# writes the result the [verify] block asserts on.
set -eu
echo "=== CLIENT ==="
sleep "${DEMO_STEP_DELAY:-0}"
echo "  >> connecting to the server"
sleep "${DEMO_STEP_DELAY:-0}"
printf '{"result": "ok"}\n' > "$DEMO_RUNTIME_DIR/handoff.json"
echo "  ** wrote handoff.json"
sleep "${DEMO_STEP_DELAY:-0}"
echo "  ** DONE"
# Hold the final frame: like server.sh (and every three-column pane), the
# command must not exit to an interactive prompt during the take, or zsh's
# prompt hook clobbers the window's custom title ("2  CLIENT") mid-recording.
# dryrun writes handoff.json above and tears this down as soon as [verify] is
# met, so the sleep never slows the headless loop.
sleep 30
