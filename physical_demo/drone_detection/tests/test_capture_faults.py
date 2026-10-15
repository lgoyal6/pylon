"""Check RTL transport faults without a radio or native driver.
Inject subprocess streams into capture.py to exercise partial and stalled reads.
Retain complete-read controls so fault rejection cannot hide broken decoding.
"""
import io
from unittest.mock import Mock

import numpy as np
import pytest

import capture


def rtl(monkeypatch, data):
    proc = Mock(stdout=io.BytesIO(data))
    monkeypatch.setattr(capture.subprocess, "Popen", lambda *a, **kw: proc)
    return capture.RtlCapture(915_000_000, 2_048_000), proc


@pytest.mark.parametrize("data", [b"", b"\x00", b"\x00\xff\x80", b"\x00\xff"])
def test_truncated_rtl_window_is_never_delivered(monkeypatch, data):
    cap, _ = rtl(monkeypatch, data)
    assert cap.read_window(4).size == 0


def test_full_rtl_window_retains_normalization(monkeypatch):
    cap, _ = rtl(monkeypatch, bytes([0, 255, 255, 0]))
    np.testing.assert_allclose(cap.read_window(2), [-1 + 1j, 1 - 1j])


def test_fragmented_reads_are_reassembled(monkeypatch):
    cap, proc = rtl(monkeypatch, b"")
    proc.stdout = Mock(read=Mock(side_effect=[b"\x00", b"\xff\xff", b"\x00"]))
    np.testing.assert_allclose(cap.read_window(2), [-1 + 1j, 1 - 1j])


@pytest.mark.parametrize("n", [0, -1])
def test_invalid_request_rejected_before_read(monkeypatch, n):
    cap, _ = rtl(monkeypatch, b"")
    with pytest.raises(ValueError):
        cap.read_window(n)


def test_close_reaps_killed_child(monkeypatch):
    cap, proc = rtl(monkeypatch, b"")
    proc.wait.side_effect = [capture.subprocess.TimeoutExpired("rtl_sdr", 2), 0]
    cap.close()
    proc.kill.assert_called_once()
    assert proc.wait.call_count == 2


def test_stalled_device_read_is_bounded(monkeypatch):
    cap, proc = rtl(monkeypatch, b"")
    proc.stdout = Mock()
    proc.stdout.fileno.return_value = 42
    monkeypatch.setattr(capture.select, "select", lambda *a: ([], [], []))
    assert cap.read_window(4).size == 0
    proc.stdout.read.assert_not_called()
