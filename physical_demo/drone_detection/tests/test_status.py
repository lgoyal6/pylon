import json
import re

import pytest
from fastapi.testclient import TestClient

import config
import service

ISO_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


@pytest.fixture
def client():
    service.state.clear()  # isolate the module-level singleton between tests
    return TestClient(service.app)


def test_status_defaults_to_not_detected(client):
    body = client.get("/status").json()
    assert body == {"detected": False, "anomaly_score": 0.0, "since": None}


def test_sim_true_flips_status_and_sets_iso_since(client):
    client.post("/sim", json={"detected": True})
    body = client.get("/status").json()
    assert body["detected"] is True
    assert body["anomaly_score"] == config.DEFAULT_ANOMALY_SCORE
    assert ISO_Z.match(body["since"]), body["since"]


def test_sim_true_honors_explicit_anomaly_score(client):
    client.post("/sim", json={"detected": True, "anomaly_score": 0.42})
    assert client.get("/status").json()["anomaly_score"] == 0.42


def test_sim_false_clears_status(client):
    client.post("/sim", json={"detected": True})
    client.post("/sim", json={"detected": False})
    body = client.get("/status").json()
    assert body == {"detected": False, "anomaly_score": 0.0, "since": None}


def test_sim_rising_edge_publishes_detection_event(client, multicast_listener):
    listener = multicast_listener()
    client.post("/sim", json={"detected": True, "anomaly_score": 0.66})
    data, _ = listener.recvfrom(65535)
    event = json.loads(data)
    assert event["anomaly_score"] == 0.66
    assert event["node_id"] == config.NODE_ID
    assert event["band"] == "2.4GHz"
