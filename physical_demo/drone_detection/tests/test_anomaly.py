import numpy as np

from anomaly import AnomalyDetector

FS = 2_400_000
N = 24576
NB = 256
LEARN = 60


def _noise(seed, n=N):
    rng = np.random.default_rng(seed)
    return (rng.standard_normal(n) + 1j * rng.standard_normal(n)).astype(np.complex64)


def _tone(n, off_hz, amp, fs=FS):
    t = np.arange(n) / fs
    return (amp * np.exp(2j * np.pi * off_hz * t)).astype(np.complex64)


# Ambient = noise + a STATIONARY spur at +600 kHz (present in every learn window).
def _ambient(seed):
    return _noise(seed) + _tone(N, 600_000, 12.0)


def _ambient_plus_novel(seed):
    # A novel narrowband burst at a FRESH frequency the model never learned.
    return _ambient(seed) + _tone(N, -450_000, 14.0)


def _learned_detector():
    det = AnomalyDetector(sample_rate=FS, n_bins=NB, learn_windows=LEARN)
    for s in range(LEARN):
        det.evaluate(_ambient(s))
    return det


def test_featurize_is_shape_normalized_vector():
    det = AnomalyDetector(sample_rate=FS, n_bins=NB, learn_windows=LEARN)
    feat = det._featurize(_noise(0))[0]
    assert feat.shape == (NB,)
    assert abs(float(np.median(feat))) < 1e-6  # median-subtracted (shape, not level)


def test_detector_is_learning_until_buffer_full():
    det = AnomalyDetector(sample_rate=FS, n_bins=NB, learn_windows=LEARN)
    for s in range(LEARN - 1):
        result = det.evaluate(_ambient(s))
        assert result["detected"] is False
    assert det.fitted is False
    det.evaluate(_ambient(LEARN))  # fills the buffer -> fits
    assert det.fitted is True


def test_ambient_is_not_detected_after_learning():
    det = _learned_detector()
    assert det.evaluate(_ambient(999))["detected"] is False


def test_stationary_spur_is_learned_as_normal():
    # The +600 kHz spur was in every learn window; it must NOT flag in watch.
    det = _learned_detector()
    assert det.evaluate(_ambient(1000))["detected"] is False


def test_novel_narrowband_burst_is_detected():
    det = _learned_detector()
    result = det.evaluate(_ambient_plus_novel(2000))
    assert result["detected"] is True
    assert result["anomaly_score"] > 0.0
    assert result["occupied_bw_hz"] > 0  # event metrics still populated


# --- quantile baseline (robust to bursty/intermittent ambient, e.g. 2.4 GHz WiFi) ---

def _bursty_ambient(seed, burst_on):
    """Noise; a +600 kHz 'WiFi-like' burst present only intermittently."""
    x = _noise(seed)
    if burst_on:
        x = x + _tone(N, 600_000, 12.0)
    return x.astype(np.complex64)


def _quantile_detector():
    det = AnomalyDetector(sample_rate=FS, n_bins=NB, learn_windows=LEARN, baseline="quantile")
    for s in range(LEARN):
        det.evaluate(_bursty_ambient(s, burst_on=(s % 3 != 0)))  # burst in ~2/3 of windows
    return det


def test_quantile_learns_intermittent_burst_as_normal():
    # A burst identical to the learned (bursty) ambient must NOT flag - it sits
    # under the learned per-bin ceiling. (mean/std would be twitchier here.)
    det = _quantile_detector()
    assert det.fitted is True
    assert det.evaluate(_bursty_ambient(999, burst_on=True))["detected"] is False


def test_quantile_flags_novel_emitter_above_ceiling():
    det = _quantile_detector()
    result = det.evaluate(_bursty_ambient(2000, burst_on=True) + _tone(N, -450_000, 14.0))
    assert result["detected"] is True
    assert result["anomaly_score"] > 0.0


def test_quantile_save_load_round_trip(tmp_path):
    det = _quantile_detector()
    path = str(tmp_path / "q_baseline.npz")
    det.save(path)
    loaded = AnomalyDetector(sample_rate=FS, n_bins=NB, learn_windows=LEARN, baseline="quantile")
    loaded.load(path)
    assert loaded.fitted is True
    assert loaded.evaluate(_bursty_ambient(2000, burst_on=True) + _tone(N, -450_000, 14.0))["detected"] is True
    assert loaded.evaluate(_bursty_ambient(999, burst_on=True))["detected"] is False


def test_save_and_load_round_trip(tmp_path):
    det = _learned_detector()
    path = str(tmp_path / "baseline.npz")
    det.save(path)

    loaded = AnomalyDetector(sample_rate=FS, n_bins=NB, learn_windows=LEARN)
    loaded.load(path)  # skips learning
    assert loaded.fitted is True
    assert loaded.evaluate(_ambient_plus_novel(2000))["detected"] is True
    assert loaded.evaluate(_ambient(999))["detected"] is False
