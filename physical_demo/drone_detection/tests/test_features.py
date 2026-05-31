"""Feature extraction: IQ window-stack -> 8-number feature vector.

Tested against the beacon waveforms — the real test of a feature set is that
distinct signal types land in distinct regions.
"""
import numpy as np

import config
from beacon import band_limited_noise, gfsk_hopper, tone
from features import FEATURE_NAMES, stack_features, window_features

FS = config.SAMPLE_RATE_HZ
N = config.WINDOW_SAMPLES


def _noise_window(seed):
    rng = np.random.default_rng(seed)
    return (rng.standard_normal(N) + 1j * rng.standard_normal(N)).astype(np.complex64)


def test_feature_vector_has_expected_length_and_order():
    vec = stack_features([_noise_window(0) for _ in range(4)], FS)
    assert len(FEATURE_NAMES) == 8
    assert vec.shape == (8,)


def test_window_features_has_all_per_window_keys():
    f = window_features(tone(N, FS, 200_000), FS)
    for k in ("occupied_bw", "flatness", "snr", "centroid", "spread", "n_peaks"):
        assert k in f


def test_noise_is_flatter_than_tone():
    i = FEATURE_NAMES.index("flatness")
    noise = stack_features([_noise_window(s) for s in range(6)], FS)
    tones = stack_features([tone(N, FS, 200_000) for _ in range(6)], FS)
    assert noise[i] > tones[i]


def test_hopper_hops_but_tone_does_not():
    # hop_rate is the temporal feature that separates a hopper from a steady tone.
    i = FEATURE_NAMES.index("hop_rate")
    hopper = stack_features([gfsk_hopper(N, FS, seed=s) for s in range(8)], FS)
    tones = stack_features([tone(N, FS, 200_000) for _ in range(8)], FS)
    assert hopper[i] > tones[i]
    assert tones[i] == 0.0  # a fixed tone never hops


def test_barrage_is_wider_than_tone():
    i = FEATURE_NAMES.index("occupied_bw")
    barrage = stack_features([band_limited_noise(N, FS, 0.4 * FS, seed=s) for s in range(6)], FS)
    tones = stack_features([tone(N, FS, 200_000) for _ in range(6)], FS)
    assert barrage[i] > tones[i]
