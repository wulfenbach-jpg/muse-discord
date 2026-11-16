#!/usr/bin/env bash
# muse-discord main-chat relay (bridge fork; BRIDGE.md, "The relay").
# Wakes the owner's MAIN chat when the reply worker relayed an owner's
# Discord request it can't do itself (scheduled jobs, the shell, files,
# memory). The state lives in main_requests.json, kept by
# bin/discord-api.py: relay-pending prints the wake payload and leases
# each request for 30 minutes (the main chat closes it with relay-done).
# Zero tokens while nothing is relayed: one file test.
#
# Register it like hooks/update-watch.sh (60 s, delivered to the main
# chat) with the wake prompt in BRIDGE.md.
set -euo pipefail
# shellcheck source=/dev/null
source "$HATCH_HOOK_RUNTIME"

PKG_DIR="${MUSE_DISCORD_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
[ -s "$PKG_DIR/main_requests.json" ] || silent "nothing relayed" '{}'
PY="$PKG_DIR/.venv/bin/python3"
[ -x "$PY" ] || PY=python3
if ! payload=$("$PY" "$PKG_DIR/bin/discord-api.py" relay-pending); then
    log "relay-pending failed" '{}'
    silent "relay-pending failed" '{}'
fi
[ -n "$payload" ] || silent "relayed requests already handed out" '{}'
wake "muse-discord: the owner asked from Discord" "$payload"
