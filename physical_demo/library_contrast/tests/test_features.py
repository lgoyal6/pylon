"""Check spectral features used by both evaluation runners.
Use synthetic.py inputs and direct boundary fixtures for features.py.
Require finite outputs for quiet IQ and reject corrupt data or bad geometry.
"""
from __future__ import annotations

import numpy as np

import config
import features
import synthetic
import pytest


def test_iq_to_windows_shape(short_duration):
    iq = synthetic.generate("ambient", duration_s=short_duration, seed=0)
    windows = features.iq_to_windows(iq)
    assert windows.ndim == 2
    assert windows.shape[1] == config.WINDOW_SAMPLES
    assert windows.dtype == np.complex64


def test_iq_to_windows_handles_too_short_input():
    short = np.zeros(config.WINDOW_SAMPLES - 1, dtype=np.complex64)
    out = features.iq_to_windows(short)
    assert out.shape == (0, config.WINDOW_SAMPLES)


def test_iq_to_windows_rejects_non_1d():
    bad = np.zeros((4, 8), dtype=np.complex64)
    try:
        features.iq_to_windows(bad)
    except ValueError:
        return
    raise AssertionError("expected ValueError on 2-D input")


def test_iq_to_features_shape_and_dtype(short_duration):
    iq = synthetic.generate("wifi", duration_s=short_duration, seed=1)
    X = features.iq_to_features(iq)
    assert X.dtype == np.float32
    assert X.ndim == 2
    assert X.shape[1] == features.feature_dim()
    assert X.shape[0] > 0


def test_features_finite_for_all_classes(short_duration):
    for name in config.ALL_CLASSES:
        iq = synthetic.generate(name, duration_s=short_duration, seed=42)
        X = features.iq_to_features(iq)
        assert np.isfinite(X).all(), f"non-finite features for class {name}"


def test_ambient_and_emitter_features_differ(short_duration):
    """Sanity check - the synthetic classes had better be separable in feature space."""
    amb = features.iq_to_features(synthetic.generate("ambient", duration_s=short_duration, seed=0))
    wifi = features.iq_to_features(synthetic.generate("wifi", duration_s=short_duration, seed=0))
    # Total spectral power should differ meaningfully (wifi >> ambient).
    assert wifi.mean(axis=0)[:config.N_PSD_BINS].mean() > amb.mean(axis=0)[:config.N_PSD_BINS].mean()


@pytest.mark.parametrize("kwargs", [{"hop_samples": 0}, {"window_samples": 0}, {"n_bins": 0}, {"n_bins": 2048}])
def test_invalid_feature_geometry_rejected(kwargs):
    with pytest.raises(ValueError):
        features.iq_to_features(np.ones(2048, complex), **kwargs)


def test_corrupt_sample_is_rejected_before_fft():
    with pytest.raises(ValueError, match="nonfinite"):
        features.iq_to_features(np.full(2048, np.nan + 1j))


def test_quiet_zero_samples_have_finite_features():
    assert np.isfinite(features.iq_to_features(np.zeros(2048, complex))).all()


def test_dense_windows_are_rejected_before_large_allocation(monkeypatch):
    iq = np.zeros(12288, dtype=np.complex64)
    def forbid_allocation(*args, **kwargs):
        raise AssertionError("large window allocation reached")
    monkeypatch.setattr(features.np, "empty", forbid_allocation)
    with pytest.raises(ValueError, match="128 MiB"):
        features.iq_to_windows(iq, window_samples=2048, hop_samples=1)
