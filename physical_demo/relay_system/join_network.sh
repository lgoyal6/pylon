#!/usr/bin/env bash
# join_network.sh — join an existing mesh as a peer / observer.
#
# Usage:
#   ./join_network.sh <bootstrap-host:port>          # join, just print messages
#   ./join_network.sh <bootstrap-host:port> 6001     # join + forward to a local
#                                                    # viz service on UDP 6001
#
# The bootstrap address is whatever the host running create_network.sh prints.
# You can also set BOOTSTRAP=host:port via env.
#
# Overrides:
#   BOOTSTRAP=host:port  alternative to passing as $1
#   NODE_ID=<name>       displayed node id (default: random short id)
#   ADVERTISE_IP=...     override auto-detected LAN IP
#   VERBOSE=1            log every send/receive

set -euo pipefail
cd "$(dirname "$0")"
export PYTHONUNBUFFERED=1

BOOTSTRAP="${1:-${BOOTSTRAP:-}}"
if [[ -z "$BOOTSTRAP" ]]; then
    cat <<EOF >&2
Usage: $0 <bootstrap-host:port> [sink-port]
       (or set BOOTSTRAP env var)
EOF
    exit 1
fi
shift || true

SINK_PORT="${1:-${SINK_PORT:-}}"
[[ $# -gt 0 ]] && shift || true

extra=()
[[ -n "${NODE_ID:-}" ]]      && extra+=(--id "$NODE_ID")
[[ -n "$SINK_PORT" ]]        && extra+=(--sink-port "$SINK_PORT")
[[ -n "${ADVERTISE_IP:-}" ]] && extra+=(--advertise-ip "$ADVERTISE_IP")
[[ "${VERBOSE:-0}" == "1" ]] && extra+=(-v)

echo "[join_network] bootstrap : $BOOTSTRAP"
[[ -n "$SINK_PORT" ]] && echo "[join_network] sink port : $SINK_PORT (udp://127.0.0.1:$SINK_PORT)"
echo

exec python3 node.py --bootstrap "$BOOTSTRAP" "${extra[@]}" "$@"
