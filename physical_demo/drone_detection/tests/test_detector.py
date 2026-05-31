import numpy as np

import config
from detector import (
    EnergyThresholdDetector,
    classify_emitter,
    psd_metrics,
    spectral_flatness,
    welch_psd,
)

FS = 2_400_000
N = 24576  # ~10 ms at 2.4 MHz


def _noise(seed, amp=1.0, n=N):
    rng = np.random.default_rng(seed)
    return (rng.standard_normal(n) + 1j * rng.standard_normal(n)).astype(np.complex64) * amp


def _tone(seed, freq_offset_hz, amp, n=N, fs=FS):
    """A single CW tone (≈one bin) — models an RTL spur, not a real emitter."""
    t = np.arange(n) / fs
    return _noise(seed) + (amp * np.exp(2j * np.pi * freq_offset_hz * t)).astype(np.complex64)


def _wideband(seed, center_off_hz, bw_hz, amp, n=N, fs=FS):
    """Band-limited signal occupying ~bw_hz — models a real emitter (e.g. FM)."""
    rng = np.random.default_rng(seed)
    x = rng.standard_normal(n) + 1j * rng.standard_normal(n)
    X = np.fft.fft(x)
    freqs = np.fft.fftfreq(n, 1 / fs)
    X[np.abs(freqs - center_off_hz) > bw_hz / 2] = 0
    y = np.fft.ifft(X)
    y = y / np.sqrt(np.mean(np.abs(y) ** 2)) * amp  # normalize power, then scale
    return (y + _noise(seed + 1)).astype(np.complex64)


def test_pure_noise_is_not_detected():
    det = EnergyThresholdDetector(sample_rate=FS)
    result = det.evaluate(_noise(0))
    assert result["detected"] is False
    assert result["occupied_bw_hz"] < det.min_occupied_bw_hz


def test_narrowband_spur_is_not_detected():
    # A lone strong CW peak (RTL spur) occupies almost no bandwidth -> reject.
    det = EnergyThresholdDetector(sample_rate=FS)
    result = det.evaluate(_tone(1, freq_offset_hz=300_000, amp=30.0))
    assert result["detected"] is False
    assert result["occupied_bw_hz"] < det.min_occupied_bw_hz


def test_wideband_signal_is_detected():
    det = EnergyThresholdDetector(sample_rate=FS)
    result = det.evaluate(_wideband(2, center_off_hz=200_000, bw_hz=200_000, amp=6.0))
    assert result["detected"] is True
    assert result["occupied_bw_hz"] >= det.min_occupied_bw_hz
    assert 0.0 < result["anomaly_score"] <= 1.0


def test_dc_offset_alone_is_not_detected():
    # A large constant (DC / RTL LO-leakage) must NOT trigger; welch detrends it.
    det = EnergyThresholdDetector(sample_rate=FS)
    assert det.evaluate(_noise(7) + (50.0 + 0j))["detected"] is False


def test_anomaly_score_is_clamped_to_unit_interval():
    det = EnergyThresholdDetector(sample_rate=FS, score_scale_hz=50_000)
    result = det.evaluate(_wideband(3, center_off_hz=0, bw_hz=400_000, amp=10.0))
    assert result["anomaly_score"] == 1.0


# --- spectral flatness + jamming-vs-comms characterization -------------------

def test_spectral_flatness_high_for_noise():
    _, psd = welch_psd(_noise(0), FS, 4096)
    assert spectral_flatness(psd) > 0.4  # a flat (noise-like) spectrum -> near 1


def test_tone_is_less_flat_than_noise():
    # A dominant CW spike pulls the geometric/arithmetic-mean ratio down.
    _, psd_noise = welch_psd(_noise(0), FS, 4096)
    _, psd_tone = welch_psd(_tone(1, freq_offset_hz=300_000, amp=50.0), FS, 4096)
    assert spectral_flatness(psd_tone) < spectral_flatness(psd_noise)


def test_classify_wideband_noise_as_jamming_like():
    # Barrage-style: noise-like energy across a wide swath (kept <50% of the band
    # so median-based occupancy stays valid — full-band barrage is detected by the
    # per-bin anomaly baseline instead).
    _, psd = welch_psd(_wideband(2, center_off_hz=0, bw_hz=1_000_000, amp=6.0), FS, 4096)
    m = psd_metrics(psd, FS, config.OCCUPANCY_MARGIN_DB)
    assert classify_emitter(m["occupied_bw_hz"], m["flatness"], FS) == "jamming-like"


def test_classify_narrowband_as_comms_like():
    _, psd = welch_psd(_wideband(2, center_off_hz=200_000, bw_hz=200_000, amp=6.0), FS, 4096)
    m = psd_metrics(psd, FS, config.OCCUPANCY_MARGIN_DB)
    assert classify_emitter(m["occupied_bw_hz"], m["flatness"], FS) == "comms-like"


def test_classify_quiet_as_unknown():
    assert classify_emitter(0, 0.9, FS) == "unknown"


def test_psd_metrics_includes_flatness():
    _, psd = welch_psd(_noise(0), FS, 4096)
    assert "flatness" in psd_metrics(psd, FS, config.OCCUPANCY_MARGIN_DB)


def test_evaluate_includes_classification():
    det = EnergyThresholdDetector(sample_rate=FS)
    result = det.evaluate(_wideband(2, center_off_hz=200_000, bw_hz=200_000, amp=6.0))
    assert result["classification"] == "comms-like"
