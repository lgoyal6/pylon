"""Iteration 1 detector: a "dumb" occupied-bandwidth energy threshold.

Computes a smoothed power spectrum (Welch) for an IQ window, measures how much
bandwidth sits above the noise floor, and detects when a real emitter occupies
>= `min_occupied_bw_hz`. Peak SNR alone is NOT the decision: on RTL-SDR the
peak-over-median is ~the same for a strong station and empty spectrum (spurs,
band shape), so it can't discriminate. Occupied bandwidth can — and it rejects
single-bin spurs and the DC spike (welch detrends DC) for free. snr_db is still
reported as a metric.

This is just a power meter — the open-world anomaly model (Iteration 2) replaces
`evaluate()` behind the same `DetectionState` seam, so its output dict mirrors
the detection-event metrics.
"""
import numpy as np
from scipy.signal import welch

import config


def welch_psd(iq: np.ndarray, sample_rate: float, nperseg: int):
    """Two-sided Welch power spectral density of an IQ window."""
    nperseg = min(nperseg, len(iq))
    f, psd = welch(iq, fs=sample_rate, nperseg=nperseg, return_onesided=False)
    return f, psd


def spectral_flatness(psd: np.ndarray) -> float:
    """Wiener entropy: geometric-mean / arithmetic-mean of the PSD, in (0, 1].
    ~1 for a flat, noise-like spectrum (barrage jamming); near 0 for a peaked,
    tonal/structured one (a CW or narrowband comms signal)."""
    p = np.asarray(psd, dtype=float)
    p = p[p > 0]
    if p.size == 0:
        return 0.0
    geo_mean = float(np.exp(np.mean(np.log(p))))
    arith_mean = float(np.mean(p))
    return geo_mean / arith_mean if arith_mean > 0 else 0.0


def classify_emitter(
    occupied_bw_hz: float,
    flatness: float,
    sample_rate: float,
    jamming_bw_frac: float = config.JAMMING_BW_FRAC,
) -> str:
    """Coarse, behavioral label for a *flagged* anomaly (not a signature match).
    Gates on occupied-bandwidth fraction: wide novel energy -> "jamming-like"
    (a barrage or a swept jammer), narrow/channelized -> "comms-like".

    `flatness` is reported alongside as a noise-like-vs-structured descriptor but
    is deliberately NOT the gate: a clean swept jammer (chirp) is wideband yet
    spectrally peaked, so a flatness gate would misread it as comms. Telling a
    swept jammer from a genuinely wideband comms signal needs temporal features
    (moving-peak tracking) — future work."""
    bw_frac = occupied_bw_hz / sample_rate if sample_rate else 0.0
    if bw_frac >= jamming_bw_frac:
        return "jamming-like"
    if occupied_bw_hz > 0:
        return "comms-like"
    return "unknown"


def psd_metrics(psd: np.ndarray, sample_rate: float, occupancy_margin_db: float) -> dict:
    """Shared event metrics derived from a PSD: peak-over-floor SNR, the bandwidth
    occupied above the noise floor, and spectral flatness (jamming-vs-comms cue).
    Native types (JSON-serializable)."""
    noise_floor = float(np.median(psd))
    peak = float(np.max(psd))
    snr_db = 10.0 * np.log10(peak / noise_floor) if noise_floor > 0 else 0.0
    bin_hz = sample_rate / len(psd)
    occupancy_cut = noise_floor * 10 ** (occupancy_margin_db / 10)
    occupied_bw_hz = float(np.count_nonzero(psd > occupancy_cut) * bin_hz)
    return {
        "snr_db": float(round(snr_db, 1)),
        "occupied_bw_hz": int(round(occupied_bw_hz)),
        "flatness": float(round(spectral_flatness(psd), 3)),
    }


class EnergyThresholdDetector:
    def __init__(
        self,
        sample_rate: float,
        nperseg: int = config.FFT_NPERSEG,
        occupancy_margin_db: float = config.OCCUPANCY_MARGIN_DB,
        min_occupied_bw_hz: float = config.MIN_OCCUPIED_BW_HZ,
        score_scale_hz: float = config.OCCUPANCY_SCORE_SCALE_HZ,
    ) -> None:
        self.sample_rate = sample_rate
        self.nperseg = nperseg
        self.occupancy_margin_db = occupancy_margin_db
        self.min_occupied_bw_hz = min_occupied_bw_hz
        self.score_scale_hz = score_scale_hz

    def evaluate(self, iq: np.ndarray) -> dict:
        """Score one IQ window. Returns detection + the real event metrics."""
        _, psd = welch_psd(iq, self.sample_rate, self.nperseg)
        metrics = psd_metrics(psd, self.sample_rate, self.occupancy_margin_db)
        occupied_bw_hz = metrics["occupied_bw_hz"]
        anomaly_score = min(max(occupied_bw_hz / self.score_scale_hz, 0.0), 1.0)
        return {
            "detected": bool(occupied_bw_hz >= self.min_occupied_bw_hz),
            "anomaly_score": float(round(anomaly_score, 3)),
            "classification": classify_emitter(occupied_bw_hz, metrics["flatness"], self.sample_rate),
            **metrics,
        }
