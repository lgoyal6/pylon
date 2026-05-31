#!/usr/bin/env bash
# create_network.sh — start the mesh bootstrap host.
#
# Runs sensor_relay.py on a known port. This is both:
#   (a) the mesh's bootstrap target (other nodes use --bootstrap <ip>:MESH_PORT)
#   (b) the local UDP ingress (SENSOR_PORT) the drone detector relays into
#
# Other machines on the same Wi-Fi join with:
#   ./join_network.sh <this-host-ip>:$MESH_PORT
#
# The drone detector on this same host bridges in with:
#   ./run_detector.sh         # uses SENSOR_PORT below
#
# Overrides:
#   MESH_PORT=5000      UDP port to bind the mesh socket
#   SENSOR_PORT=5050    UDP port for local sensor ingress (incl. drone events)
#   NODE_ID=hub         displayed node id
#   ADVERTISE_IP=...    override auto-detected LAN IP

set -euo pipefail
cd "$(dirname "$0")"
export PYTHONUNBUFFERED=1

MESH_PORT="${MESH_PORT:-5000}"
SENSOR_PORT="${SENSOR_PORT:-5050}"
NODE_ID="${NODE_ID:-hub}"

extra=()
if [[ -n "${ADVERTISE_IP:-}" ]]; then
    extra+=(--advertise-ip "$ADVERTISE_IP")
fi

echo "[create_network] mesh port     : $MESH_PORT"
echo "[create_network] sensor port   : $SENSOR_PORT"
echo "[create_network] node id       : $NODE_ID"
echo "[create_network] other machines: ./join_network.sh <this-ip>:$MESH_PORT"
echo "[create_network] local detector: ./run_detector.sh"
echo

exec python3 sensor_relay.py \
    --id "$NODE_ID" \
    --port "$MESH_PORT" \
    --sensor-port "$SENSOR_PORT" \
    "${extra[@]}" \
    "$@"
