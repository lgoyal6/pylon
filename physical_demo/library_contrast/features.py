"""IQ → per-window spectral feature vectors.

Each window becomes one row: a downsampled log-PSD plus a few summary stats.
RandomForest and IsolationForest both eat this directly.
"""
from __future__ import annotations

import numpy as np

import config


def iq_to_windows(
    iq: np.ndarray,
    window_samples: int = config.WINDOW_SAMPLES,
    hop_samples: int = config.HOP_SAMPLES,
) -> np.ndarray:
    """Slide a Hann-tapered window across complex IQ; return (n_windows, window_samples) complex."""
    if iq.ndim != 1:
        raise ValueError(f"expected 1-D complex IQ, got shape {iq.shape}")
    if iq.size < window_samples:
        return np.empty((0, window_samples), dtype=np.complex64)
    taper = np.hanning(window_samples).astype(np.float32)
    n = 1 + (iq.size - window_samples) // hop_samples
    out = np.empty((n, window_samples), dtype=np.complex64)
    for i in range(n):
        start = i * hop_samples
        out[i] = iq[start : start + window_samples] * taper
    return out


def _psd_bins(window: np.ndarray, n_bins: int) -> np.ndarray:
    """log10 PSD reduced to `n_bins` by mean-pooling adjacent FFT bins."""
    spec = np.fft.fftshift(np.fft.fft(window))
    psd = np.abs(spec) ** 2
    # Mean-pool to n_bins so the feature vector is small and RF stays fast.
    pool = psd.size // n_bins
    pooled = psd[: pool * n_bins].reshape(n_bins, pool).mean(axis=1)
    return np.log10(pooled + 1e-12).astype(np.float32)


def _summary_stats(psd_bins: np.ndarray) -> np.ndarray:
    """Compact spectral descriptors that help classes separate cleanly."""
    p = 10 ** psd_bins  # back to linear power for centroid math
    total = p.sum() + 1e-12
    idx = np.arange(p.size, dtype=np.float32)
    centroid = float((idx * p).sum() / total)
    # Spread around the centroid — wide for WiFi/LoRa, narrow for BT/CW.
    spread = float(np.sqrt(((idx - centroid) ** 2 * p).sum() / total))
    peak = float(psd_bins.max())
    # Occupancy: fraction of bins within 10 dB of the peak (rough BW indicator).
    occupancy = float((psd_bins > psd_bins.max() - 1.0).mean())
    # Second-peak ratio: catches multi-tone signals like the novel dual-tone
    # CW. For a single-emitter spectrum the runner-up is just noise floor;
    # for dual-tone it's comparable to the top peak.
    sorted_desc = np.sort(p)[::-1]
    second_peak_ratio = float(sorted_desc[1] / (sorted_desc[0] + 1e-12)) if p.size > 1 else 0.0
    return np.array([centroid, spread, peak, occupancy, second_peak_ratio], dtype=np.float32)


def window_to_features(window: np.ndarray, n_bins: int = config.N_PSD_BINS) -> np.ndarray:
    psd = _psd_bins(window, n_bins)
    stats = _summary_stats(psd)
    return np.concatenate([psd, stats])


_N_SUMMARY_STATS = 5  # centroid, spread, peak, occupancy, second_peak_ratio


def iq_to_features(
    iq: np.ndarray,
    window_samples: int = config.WINDOW_SAMPLES,
    hop_samples: int = config.HOP_SAMPLES,
    n_bins: int = config.N_PSD_BINS,
) -> np.ndarray:
    """Returns (n_windows, n_bins + 5) float32 feature matrix."""
    windows = iq_to_windows(iq, window_samples, hop_samples)
    if windows.size == 0:
        return np.empty((0, n_bins + _N_SUMMARY_STATS), dtype=np.float32)
    return np.stack([window_to_features(w, n_bins) for w in windows])


def feature_dim(n_bins: int = config.N_PSD_BINS) -> int:
    """Total feature-vector length: n PSD bins + summary stats."""
    return n_bins + _N_SUMMARY_STATS
