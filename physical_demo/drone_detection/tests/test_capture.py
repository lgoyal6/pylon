"""Hardware smoke test — skips cleanly when the rtl_sdr CLI or device is absent."""
import shutil

import numpy as np
import pytest

import config
from capture import RtlCapture


@pytest.mark.skipif(shutil.which("rtl_sdr") is None, reason="rtl_sdr CLI not installed")
def test_rtl_capture_reads_iq_window_when_device_present():
    try:
        cap = RtlCapture(config.DEFAULT_CENTER_FREQ_HZ, config.SAMPLE_RATE_HZ)
    except Exception as exc:
        pytest.skip(f"cannot start rtl_sdr: {exc}")

    try:
        iq = cap.read_window(4096)
    finally:
        cap.close()

    if iq.size == 0:
        pytest.skip("no RTL-SDR device present")

    assert iq.dtype == np.complex64
    assert iq.size == 4096
    assert np.all(np.abs(iq) <= 1.5)  # normalized IQ
