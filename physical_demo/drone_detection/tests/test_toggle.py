import json

import pytest

import config
import service


@pytest.fixture(autouse=True)
def reset_state():
    service.state.clear()


def test_toggle_flips_detection_off_and_on():
    service._toggle()
    assert service.state.detected is True
    service._toggle()
    assert service.state.detected is False


def test_toggle_to_detected_publishes_event(multicast_listener):
    listener = multicast_listener()
    service._toggle()  # not-detected -> detected, should publish
    data, _ = listener.recvfrom(65535)
    event = json.loads(data)
    assert event["anomaly_score"] == config.DEFAULT_ANOMALY_SCORE
