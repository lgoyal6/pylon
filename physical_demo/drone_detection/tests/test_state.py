import re

from state import DetectionState

ISO_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


def test_default_state_is_not_detected():
    state = DetectionState()
    snap = state.snapshot()
    assert snap == {"detected": False, "anomaly_score": 0.0, "since": None}


def test_set_detected_marks_detected_with_score_and_iso_since():
    state = DetectionState()
    rising = state.set_detected(0.91)
    snap = state.snapshot()

    assert rising is True  # false -> true is a rising edge
    assert snap["detected"] is True
    assert snap["anomaly_score"] == 0.91
    assert ISO_Z.match(snap["since"]), snap["since"]


def test_set_detected_again_is_not_a_rising_edge_and_keeps_since():
    state = DetectionState()
    state.set_detected(0.5)
    first_since = state.snapshot()["since"]

    rising = state.set_detected(0.7)
    snap = state.snapshot()

    assert rising is False  # already detected
    assert snap["since"] == first_since  # since is pinned to the rising edge
    assert snap["anomaly_score"] == 0.7  # score still updates


def test_clear_resets_to_default():
    state = DetectionState()
    state.set_detected(0.9)
    state.clear()
    assert state.snapshot() == {"detected": False, "anomaly_score": 0.0, "since": None}
