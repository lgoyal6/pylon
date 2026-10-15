"""Check health and detection state when capture fails or stalls.
Inject streams into service.DetectorRunner and exercise its HTTP health view.
Require bad data to bypass scoring and stopped sources to clear detection.
"""
import threading
from unittest.mock import Mock

import numpy as np
import pytest

import service
from bus import DetectionBus
from state import DetectionState


def runner(iq=None, error=None):
    cap = Mock()
    cap.read_window.side_effect = error
    cap.read_window.return_value = iq
    det = Mock()
    state = DetectionState()
    state.set_detected(1.0)
    return service.DetectorRunner(cap, det, state, DetectionBus(), 915_000_000, window_samples=4)


def test_end_of_stream_clears_stale_detection():
    r = runner(np.array([], dtype=complex))
    assert r.step() is None
    assert not r.state.detected
    assert r.health["state"] == "ended"
    r.detector.evaluate.assert_not_called()


@pytest.mark.parametrize("iq", [np.ones(3, complex), np.full(4, np.nan + 1j), np.ones((2, 2), complex), np.ones(4)])
def test_invalid_samples_stop_without_scoring(iq):
    r = runner(iq)
    with pytest.raises(ValueError):
        r.run(threading.Event())
    assert not r.state.detected
    assert r.health["state"] == "failed"
    r.detector.evaluate.assert_not_called()
    r.capture.close.assert_called_once()


def test_device_exception_is_unhealthy_and_closes():
    r = runner(error=OSError("device removed"))
    with pytest.raises(OSError):
        r.run(threading.Event())
    assert not r.state.detected
    assert r.health["state"] == "failed"
    r.capture.close.assert_called_once()


def test_cancelled_loop_clears_detection_and_closes():
    r = runner(np.ones(4, complex))
    stop = threading.Event()
    stop.set()
    r.run(stop)
    assert not r.state.detected
    assert r.health["state"] == "stopped"
    r.capture.close.assert_called_once()


def test_live_health_without_runner_is_unavailable(monkeypatch):
    import asyncio
    monkeypatch.setattr(service, "source", "live")
    monkeypatch.setattr(service, "capture_runner", None, raising=False)
    assert asyncio.run(service.health())["state"] == "unavailable"


def test_healthy_window_has_live_age_and_stall_becomes_stale(monkeypatch):
    import asyncio
    r = runner(np.ones(4, complex))
    r.detector.evaluate.return_value = {"detected": False}
    r.step()
    monkeypatch.setattr(service, "source", "live")
    monkeypatch.setattr(service, "capture_runner", r)
    assert asyncio.run(service.health())["state"] == "running"
    r.health["last_window_monotonic"] -= 6
    assert asyncio.run(service.health())["state"] == "stale"


def test_stale_source_cannot_keep_emitting_heartbeat(monkeypatch):
    import asyncio
    r = runner(np.ones(4, complex))
    r.health.update(state="running", last_window_monotonic=service.time.monotonic() - 6)
    monkeypatch.setattr(service, "source", "live")
    monkeypatch.setattr(service, "capture_runner", r)
    service.state.set_detected(1.0)
    publish = Mock()
    monkeypatch.setattr(service, "_publish_current", publish)
    calls = 0
    async def sleep(_):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise asyncio.CancelledError
    monkeypatch.setattr(service.asyncio, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(service._heartbeat())
    assert not service.state.detected
    publish.assert_not_called()


def test_first_window_stall_is_also_visible(monkeypatch):
    import asyncio
    r = runner(np.ones(4, complex))
    r.health["started_monotonic"] -= 6
    monkeypatch.setattr(service, "source", "live")
    monkeypatch.setattr(service, "capture_runner", r)
    assert asyncio.run(service.health())["state"] == "stale"


def test_http_health_has_correlation_and_bounded_metrics(monkeypatch):
    from fastapi.testclient import TestClient
    r = runner(np.ones(4, complex))
    monkeypatch.setattr(service, "source", "live")
    monkeypatch.setattr(service, "capture_runner", r)
    response = TestClient(service.app).get("/health")
    assert response.status_code == 200
    assert set(response.json()) == {"source", "state", "run_id", "windows", "last_window_age_s"}
    assert len(response.json()["run_id"]) == 32


def test_failed_model_load_closes_opened_receiver(monkeypatch):
    import capture
    import classifier
    cap = Mock()
    monkeypatch.setattr(service, "sdr_kind", "rtl")
    monkeypatch.setattr(service, "detector_kind", "classifier")
    monkeypatch.setattr(capture, "RtlCapture", lambda **kw: cap)
    monkeypatch.setattr(classifier.RFClassifier, "load", Mock(side_effect=ValueError("bad model")))
    with pytest.raises(ValueError, match="bad model"):
        service._start_capture_thread()
    cap.close.assert_called_once()
    assert service.capture_runner is None
