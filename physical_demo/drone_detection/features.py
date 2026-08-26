"""Case 3 - feature extraction: IQ window-stack -> a compact feature vector.

Each window is summarized from its Welch PSD (reusing detector.py); a short stack
of windows adds the temporal features that single-window stats can't see
(hopping, duty). The result is one ~8-number point the classifier (train.py)
learns to separate by signal type. See README / the feature-set table.
"""
import numpy as np

import config
from detector import psd_metrics, welch_psd

FEATURE_NAMES = [
    "occupied_bw", "flatness", "snr", "centroid", "spread", "n_peaks",  # per-window (averaged)
    "hop_rate", "duty_cycle",                                           # temporal (over the stack)
]


def _centroid_spread(f: np.ndarray, psd: np.ndarray):
    """Power-weighted mean frequency and its spread (spectral shape)."""
    order = np.argsort(f)
    f, psd = f[order], psd[order]
    p = psd / (psd.sum() + 1e-12)
    centroid = float(np.sum(f * p))
    spread = float(np.sqrt(max(np.sum(((f - centroid) ** 2) * p), 0.0)))
    return centroid, spread


def _n_peaks(psd: np.ndarray, margin_db: float) -> int:
    """Count contiguous clusters of bins above the occupancy cut (1 = tone-like,
    several = multi-channel / hopper-over-window)."""
    cut = float(np.median(psd)) * 10 ** (margin_db / 10)
    above = (psd > cut).astype(int)
    if above.sum() == 0:
        return 0
    return int(np.sum(np.diff(above) == 1) + above[0])


def window_features(iq, sample_rate, nperseg: int = config.N_FEATURE_BINS,
                    margin_db: float = config.OCCUPANCY_MARGIN_DB) -> dict:
    """Per-window features from one IQ window (plus `_peak_freq` for hop tracking)."""
    f, psd = welch_psd(iq, sample_rate, nperseg)
    m = psd_metrics(psd, sample_rate, margin_db)
    centroid, spread = _centroid_spread(f, psd)
    return {
        "occupied_bw": float(m["occupied_bw_hz"]),
        "flatness": float(m["flatness"]),
        "snr": float(m["snr_db"]),
        "centroid": centroid,
        "spread": spread,
        "n_peaks": float(_n_peaks(psd, margin_db)),
        "_peak_freq": float(f[np.argmax(psd)]),
    }


def stack_features(iq_windows, sample_rate, nperseg: int = config.N_FEATURE_BINS,
                   margin_db: float = config.OCCUPANCY_MARGIN_DB) -> np.ndarray:
    """Reduce a stack of IQ windows to one feature vector (FEATURE_NAMES order):
    per-window features averaged + temporal hop_rate / duty_cycle over the stack."""
    feats = [window_features(w, sample_rate, nperseg, margin_db) for w in iq_windows]
    bin_hz = sample_rate / nperseg

    occ = np.array([fe["occupied_bw"] for fe in feats])
    peaks = np.array([fe["_peak_freq"] for fe in feats])

    # hop_rate: fraction of consecutive windows whose dominant frequency jumped >2 bins.
    hop_rate = float(np.mean(np.abs(np.diff(peaks)) > 2 * bin_hz)) if len(peaks) > 1 else 0.0
    # duty_cycle: fraction of windows carrying real occupancy (energy present).
    duty_cycle = float(np.mean(occ >= config.MIN_OCCUPIED_BW_HZ))

    return np.array([
        float(np.mean([fe["occupied_bw"] for fe in feats])),
        float(np.mean([fe["flatness"] for fe in feats])),
        float(np.mean([fe["snr"] for fe in feats])),
        float(np.mean([fe["centroid"] for fe in feats])),
        float(np.mean([fe["spread"] for fe in feats])),
        float(np.mean([fe["n_peaks"] for fe in feats])),
        hop_rate,
        duty_cycle,
    ])
