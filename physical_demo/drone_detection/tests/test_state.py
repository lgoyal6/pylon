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


def test_set_detected_stores_event_metrics():
    state = DetectionState()
    state.set_detected(0.8, center_freq_hz=433_000_000, snr_db=18.5, occupied_bw_hz=120_000)
    ev = state.event_snapshot()
    assert ev["anomaly_score"] == 0.8
    assert ev["center_freq_hz"] == 433_000_000
    assert ev["snr_db"] == 18.5
    assert ev["occupied_bw_hz"] == 120_000


def test_event_metrics_default_to_none_when_unset():
    state = DetectionState()
    ev = state.event_snapshot()
    assert ev["center_freq_hz"] is None
    assert ev["snr_db"] is None
    assert ev["occupied_bw_hz"] is None


def test_clear_resets_event_metrics():
    state = DetectionState()
    state.set_detected(0.8, center_freq_hz=433_000_000, snr_db=18.5, occupied_bw_hz=120_000)
    state.clear()
    assert state.event_snapshot()["center_freq_hz"] is None


def test_set_detected_stores_classification():
    state = DetectionState()
    state.set_detected(0.8, classification="jamming-like")
    assert state.event_snapshot()["classification"] == "jamming-like"


def test_classification_defaults_to_none_and_clears():
    state = DetectionState()
    assert state.event_snapshot()["classification"] is None
    state.set_detected(0.8, classification="comms-like")
    state.clear()
    assert state.event_snapshot()["classification"] is None
