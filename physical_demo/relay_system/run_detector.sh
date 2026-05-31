#!/usr/bin/env bash
# run_detector.sh — start the drone detector and bridge its events into the
# local mesh via sensor_relay's ingress port.
#
# Requires create_network.sh (or sensor_relay.py with the same SENSOR_PORT) to
# already be running on this host. Without that ingress listener, detection
# events have nowhere to land.
#
# Default --source sim (no SDR needed). To trigger a detection by hand once
# running, in another shell:
#   curl -X POST http://127.0.0.1:5001/sim -H content-type:application/json \
#        -d '{"detected":true}'
#
# For the real SDR path:
#   ./run_detector.sh --source live --sdr rtl     # NESDR / RTL-SDR
#   ./run_detector.sh --source live --sdr pluto   # ADALM-Pluto (2.4 GHz)
#
# Overrides:
#   SENSOR_PORT=5050   the sensor_relay ingress on this host
#   RELAY=host:port    full override (defaults to 127.0.0.1:$SENSOR_PORT)
#   NODE_ID=<name>     value advertised in each detection event

set -euo pipefail
cd "$(dirname "$0")/../drone_detection"
export PYTHONUNBUFFERED=1

SENSOR_PORT="${SENSOR_PORT:-5050}"
RELAY="${RELAY:-127.0.0.1:$SENSOR_PORT}"

[[ -n "${NODE_ID:-}" ]] && export DRONE_NODE_ID="$NODE_ID"

echo "[run_detector] relay (mesh ingress): $RELAY"
echo "[run_detector] node id             : ${NODE_ID:-${DRONE_NODE_ID:-node-1}}"
echo "[run_detector] HTTP control plane  : http://127.0.0.1:5001"
echo "[run_detector] manual toggle       : curl -XPOST :5001/sim -d '{\"detected\":true}'"
echo

exec python3 main.py --relay "$RELAY" "$@"
