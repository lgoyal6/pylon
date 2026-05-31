import json
import socket
import struct

import config
from publisher import MulticastPublisher, build_event

CONTRACT_KEYS = {
    "node_id",
    "timestamp",
    "center_freq_hz",
    "band",
    "anomaly_score",
    "threshold",
    "classification",
    "label",
    "confidence",
    "snr_db",
    "occupied_bw_hz",
}


def test_build_event_matches_full_contract_schema():
    event = build_event({"anomaly_score": 0.87})
    assert set(event) == CONTRACT_KEYS
    assert event["anomaly_score"] == 0.87
    assert event["node_id"] == config.NODE_ID
    assert event["label"] is None


def test_build_event_uses_metrics_from_snapshot_when_present():
    event = build_event(
        {
            "anomaly_score": 0.8,
            "center_freq_hz": 433_000_000,
            "snr_db": 18.5,
            "occupied_bw_hz": 120_000,
        }
    )
    assert event["center_freq_hz"] == 433_000_000
    assert event["snr_db"] == 18.5
    assert event["occupied_bw_hz"] == 120_000


def test_build_event_falls_back_to_config_defaults_when_metrics_absent():
    event = build_event({"anomaly_score": 0.5})
    assert event["center_freq_hz"] == config.CENTER_FREQ_HZ
    assert event["snr_db"] == config.SNR_DB
    assert event["occupied_bw_hz"] == config.OCCUPIED_BW_HZ


def test_build_event_uses_classification_from_snapshot():
    event = build_event({"anomaly_score": 0.8, "classification": "jamming-like"})
    assert event["classification"] == "jamming-like"


def test_build_event_classification_falls_back_to_config():
    assert build_event({"anomaly_score": 0.5})["classification"] == config.CLASSIFICATION


def _multicast_listener(group: str, port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", port))
    mreq = struct.pack("4sl", socket.inet_aton(group), socket.INADDR_ANY)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    sock.settimeout(2.0)
    return sock


def test_publisher_sends_json_datagram_to_multicast_group():
    listener = _multicast_listener(config.MCAST_GROUP, config.MCAST_PORT)
    pub = MulticastPublisher()
    try:
        pub.send(build_event({"anomaly_score": 0.5}))
        data, _ = listener.recvfrom(65535)
    finally:
        pub.close()
        listener.close()

    event = json.loads(data)
    assert set(event) == CONTRACT_KEYS
    assert event["anomaly_score"] == 0.5
    assert event["timestamp"].endswith("Z")
