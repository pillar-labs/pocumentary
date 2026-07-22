#!/bin/sh
# Stands in for the "victim infrastructure" role. Signals readiness by touching
# a file in $DEMO_RUNTIME_DIR, exactly as the CAND-003 role scripts do.
set -eu
echo "=== SERVER (victim infra) ==="
sleep "${DEMO_STEP_DELAY:-0}"
echo "  >> starting services"
sleep "${DEMO_STEP_DELAY:-0}"
echo "  ** listening on 127.0.0.1"
: > "$DEMO_RUNTIME_DIR/server_ready"
echo "  ** signalled: server_ready"
sleep 30
