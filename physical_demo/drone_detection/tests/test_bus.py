"""DetectionBus: the decoupling buffer between detection sources and the mesh sink."""
from bus import DetectionBus


def test_publish_then_get_returns_the_event():
    bus = DetectionBus()
    bus.publish({"source": "sdr", "anomaly_score": 0.5})
    ev = bus.get(timeout=0.1)
    assert ev["source"] == "sdr"
    assert ev["anomaly_score"] == 0.5


def test_get_returns_none_when_empty():
    assert DetectionBus().get(timeout=0.02) is None


def test_full_buffer_drops_newest_instead_of_blocking():
    # Detection is real-time; a full buffer drops rather than stalling a source.
    bus = DetectionBus(maxsize=1)
    bus.publish({"n": 1})
    bus.publish({"n": 2})  # dropped - must not block
    assert bus.get(timeout=0.1)["n"] == 1
    assert bus.get(timeout=0.02) is None


def test_fifo_order():
    bus = DetectionBus()
    bus.publish({"n": 1})
    bus.publish({"n": 2})
    assert bus.get(timeout=0.1)["n"] == 1
    assert bus.get(timeout=0.1)["n"] == 2
