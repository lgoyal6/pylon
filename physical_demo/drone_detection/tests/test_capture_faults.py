"""Check RTL and Pluto faults without a radio or native driver.
Inject streams and receiver setup faults into capture.py to check cleanup.
Retain complete-read controls so fault rejection cannot hide broken decoding.
"""
import io
import sys
from types import SimpleNamespace
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


@pytest.mark.parametrize("attribute", [
    "rx_lo", "sample_rate", "rx_rf_bandwidth",
    "gain_control_mode_chan0", "rx_hardwaregain_chan0",
])
@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_pluto_setup_failure_closes_opened_receiver(monkeypatch, attribute, cleanup_fails):
    class FaultySdr:
        def __setattr__(self, name, value):
            if name == attribute:
                raise OSError("injected setup failure: " + attribute)
            object.__setattr__(self, name, value)

    sdr = FaultySdr()
    sdr.rx_destroy_buffer = Mock(side_effect=RuntimeError("cleanup failed") if cleanup_fails else None)
    opened = Mock(return_value=sdr)
    monkeypatch.setitem(sys.modules, "adi", SimpleNamespace(Pluto=opened))
    with pytest.raises(OSError, match="injected setup failure: " + attribute):
        capture.PlutoCapture(2_437_000_000, 4_000_000, gain="40", uri="fake-uri")
    opened.assert_called_once_with("fake-uri")
    sdr.rx_destroy_buffer.assert_called_once()
