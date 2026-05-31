"""UDP multicast publisher for detection events.

Builds the detection-event JSON (the contract the teammate's relay consumes) and
sends it to the multicast group. Iteration 0 fills the RF fields with the static
stub values from `config`; the schema is what stays fixed for the relay.
"""
import json
import socket

import config
from state import iso_now


def _metric(snapshot: dict, key: str, default):
    """Real metric from the snapshot, or the config stub when the detector
    hasn't supplied one (e.g. the /sim path)."""
    value = snapshot.get(key)
    return value if value is not None else default


def build_event(snapshot: dict) -> dict:
    """Assemble a detection event from the current state snapshot + config.

    Real RF metrics (center_freq_hz, snr_db, occupied_bw_hz) come from the
    snapshot when present; otherwise the config stub values keep the schema
    stable (Iteration 0 / manual /sim behavior)."""
    return {
        "node_id": config.NODE_ID,
        "timestamp": iso_now(),
        "center_freq_hz": _metric(snapshot, "center_freq_hz", config.CENTER_FREQ_HZ),
        "band": config.BAND,
        "anomaly_score": snapshot["anomaly_score"],
        "threshold": config.THRESHOLD,
        "classification": _metric(snapshot, "classification", config.CLASSIFICATION),
        "label": config.LABEL,
        "confidence": config.CONFIDENCE,
        "snr_db": _metric(snapshot, "snr_db", config.SNR_DB),
        "occupied_bw_hz": _metric(snapshot, "occupied_bw_hz", config.OCCUPIED_BW_HZ),
    }


class MulticastPublisher:
    def __init__(self, group: str = None, port: int = None, ttl: int = None,
                 relay_addr=None) -> None:
        self.addr = (group or config.MCAST_GROUP, port or config.MCAST_PORT)
        # (host, port) of a mesh sensor-relay ingress to also unicast events to.
        self.relay_addr = relay_addr if relay_addr is not None else config.RELAY_ADDR
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.sock.setsockopt(
            socket.IPPROTO_IP,
            socket.IP_MULTICAST_TTL,
            ttl if ttl is not None else config.MCAST_TTL,
        )
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)

    def send(self, event: dict) -> None:
        payload = json.dumps(event).encode("utf-8")
        self.sock.sendto(payload, self.addr)
        if self.relay_addr is not None:  # bridge into the mesh via the sensor relay
            self.sock.sendto(payload, self.relay_addr)

    def close(self) -> None:
        self.sock.close()
