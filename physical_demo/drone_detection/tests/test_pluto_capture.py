"""PlutoCapture unit tests.

A fake SDR is injected so these run without libiio or a Pluto attached — they
exercise the tuning/normalization/buffer logic, not the hardware. The live path
builds adi.Pluto itself (lazy import), covered separately by a hardware smoke test.
"""
import numpy as np

from capture import PlutoCapture


class FakeSdr:
    """Stand-in for adi.Pluto: accepts configured attrs, returns canned IQ."""

    def __init__(self, samples):
        self._samples = np.asarray(samples)
        self.rx_buffer_size = 0
        self.destroyed = False

    def rx(self):
        return self._samples[: self.rx_buffer_size]

    def rx_destroy_buffer(self):
        self.destroyed = True


def test_read_window_returns_normalized_complex64_of_requested_length():
    # Pluto's rx() yields int16-range complex (12-bit ADC, |sample| up to ~2048).
    raw = (np.full(8, 2048.0) + 1j * np.zeros(8)).astype(np.complex128)
    cap = PlutoCapture(center_freq_hz=2_437_000_000, sample_rate=4_000_000, sdr=FakeSdr(raw))
    iq = cap.read_window(8)
    assert iq.dtype == np.complex64
    assert iq.size == 8
    assert np.allclose(np.abs(iq), 1.0, atol=0.01)  # 2048 / 2048 -> ~1.0


def test_constructor_tunes_the_radio():
    sdr = FakeSdr(np.zeros(4, dtype=np.complex128))
    PlutoCapture(center_freq_hz=2_437_000_000, sample_rate=4_000_000, sdr=sdr)
    assert sdr.rx_lo == 2_437_000_000
    assert sdr.sample_rate == 4_000_000
    assert sdr.rx_rf_bandwidth == 4_000_000


def test_read_window_sets_buffer_size():
    sdr = FakeSdr(np.zeros(16, dtype=np.complex128))
    cap = PlutoCapture(center_freq_hz=2_437_000_000, sample_rate=4_000_000, sdr=sdr)
    cap.read_window(16)
    assert sdr.rx_buffer_size == 16


def test_auto_gain_uses_agc():
    sdr = FakeSdr(np.zeros(4, dtype=np.complex128))
    PlutoCapture(2_437_000_000, 4_000_000, gain="auto", sdr=sdr)
    assert sdr.gain_control_mode_chan0 == "slow_attack"


def test_manual_gain_sets_hardwaregain():
    sdr = FakeSdr(np.zeros(4, dtype=np.complex128))
    PlutoCapture(2_437_000_000, 4_000_000, gain="40", sdr=sdr)
    assert sdr.gain_control_mode_chan0 == "manual"
    assert sdr.rx_hardwaregain_chan0 == 40.0


def test_close_destroys_buffer():
    sdr = FakeSdr(np.zeros(4, dtype=np.complex128))
    cap = PlutoCapture(center_freq_hz=2_437_000_000, sample_rate=4_000_000, sdr=sdr)
    cap.close()
    assert sdr.destroyed is True
