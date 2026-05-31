"""Beacon tests.

Waveform generators are deterministic (no hardware). PlutoBeacon's TX wrapper is
exercised with an injected fake SDR, so these run without libiio or a Pluto.
"""
import numpy as np

from beacon import PlutoBeacon, apply_duty, band_limited_noise, chirp, tone


class FakeSdr:
    """Stand-in for adi.Pluto on the TX side: records what was transmitted."""

    def __init__(self):
        self.tx_cyclic_buffer = False
        self.transmitted = None
        self.tx_destroyed = False

    def tx(self, samples=None):
        self.transmitted = samples

    def tx_destroy_buffer(self):
        self.tx_destroyed = True


# --- waveform generators ----------------------------------------------------

def test_tone_has_peak_at_offset_frequency():
    fs, n, offset = 2_000_000, 4096, 200_000
    x = tone(n, fs, offset)
    assert x.dtype == np.complex64
    assert x.size == n
    spec = np.abs(np.fft.fft(x))
    freqs = np.fft.fftfreq(n, 1 / fs)
    peak_freq = freqs[np.argmax(spec)]
    assert abs(peak_freq - offset) < fs / n  # within one FFT bin


def test_tone_amplitude_bounded():
    x = tone(1024, 2_000_000, 100_000, amplitude=0.5)
    assert np.max(np.abs(x)) <= 0.51


def test_band_limited_noise_keeps_energy_inside_the_band():
    fs, n, bw = 2_000_000, 8192, 200_000
    x = band_limited_noise(n, fs, bw, seed=0)
    assert x.dtype == np.complex64
    assert x.size == n
    spec = np.abs(np.fft.fft(x)) ** 2
    freqs = np.fft.fftfreq(n, 1 / fs)
    in_band = np.abs(freqs) <= bw / 2
    assert spec[in_band].sum() / spec.sum() > 0.9  # most power inside ±bw/2


def test_chirp_sweeps_energy_across_the_band():
    fs, n, bw = 2_000_000, 8192, 1_000_000
    x = chirp(n, fs, bw)
    assert x.dtype == np.complex64
    assert x.size == n
    spec = np.abs(np.fft.fft(x)) ** 2
    freqs = np.fft.fftfreq(n, 1 / fs)
    in_band = np.abs(freqs) <= bw / 2
    assert spec[in_band].sum() / spec.sum() > 0.8          # energy within the swept band
    assert np.mean(spec > spec.max() * 0.1) > 0.1          # spread across bins, not one


def test_apply_duty_gates_off_the_tail():
    wf = tone(1000, 2_000_000, 100_000, amplitude=1.0)
    gated = apply_duty(wf, 0.5)
    assert np.all(gated[500:] == 0)      # off for the back half (sporadic / pulsed)
    assert np.any(gated[:500] != 0)      # on for the front half


def test_apply_duty_one_is_passthrough():
    wf = tone(128, 2_000_000, 100_000)
    assert np.array_equal(apply_duty(wf, 1.0), wf)


# --- PlutoBeacon TX wrapper -------------------------------------------------

def test_beacon_constructor_configures_tx():
    sdr = FakeSdr()
    PlutoBeacon(center_freq_hz=433_920_000, sample_rate=2_000_000, tx_atten_db=-40, sdr=sdr)
    assert sdr.tx_lo == 433_920_000
    assert sdr.sample_rate == 2_000_000
    assert sdr.tx_rf_bandwidth == 2_000_000
    assert sdr.tx_hardwaregain_chan0 == -40.0


def test_start_transmits_scaled_cyclic_waveform():
    sdr = FakeSdr()
    b = PlutoBeacon(433_920_000, 2_000_000, sdr=sdr)
    b.start(tone(1024, 2_000_000, 100_000, amplitude=1.0))
    assert sdr.tx_cyclic_buffer is True
    assert sdr.transmitted is not None
    assert np.max(np.abs(sdr.transmitted)) > 1000  # scaled up to Pluto's int16 range


def test_stop_destroys_tx_buffer():
    sdr = FakeSdr()
    b = PlutoBeacon(433_920_000, 2_000_000, sdr=sdr)
    b.stop()
    assert sdr.tx_destroyed is True
