"""Iteration 2 detector: open-world RF anomaly detection (the product).

Learns the ambient spectrum as "normal" — a per-frequency-bin baseline
(mean/std of the normalized PSD shape) — then flags a window when any bin's
power rises far above its learned baseline (max z-score). This catches an
*unknown* emitter a signature library would miss. Stationary spurs/ambient seen
during learning are baked into the baseline, so they stop false-alarming (the
Iteration 1 spur problem). A bursty narrowband emitter (e.g. a key fob)
introduces energy in a bin that was quiet -> a huge z -> flagged.

Why not IsolationForest (the original plan): on RTL data a novel narrowband
burst is a single anomalous bin among ~256 feature dims, and IF's random splits
almost never isolate it (measured: a 141-sigma bin produced no change in IF
score). The learned per-bin baseline is far more sensitive and just as
unsupervised.

Same `evaluate(iq) -> {detected, anomaly_score, snr_db, occupied_bw_hz}` contract
as EnergyThresholdDetector, so it drops into DetectorRunner unchanged. The
learn->watch transition is self-managed by counting windows; during learning it
returns detected=False.
"""
import numpy as np

import config
from detector import classify_emitter, psd_metrics, welch_psd


class AnomalyDetector:
    def __init__(
        self,
        sample_rate: float,
        n_bins: int = config.N_FEATURE_BINS,
        learn_windows: int = 3000,
        z_threshold: float = config.Z_THRESHOLD,
        z_score_scale: float = config.Z_SCORE_SCALE,
        sigma_floor_db: float = config.SIGMA_FLOOR_DB,
        occupancy_margin_db: float = config.OCCUPANCY_MARGIN_DB,
    ) -> None:
        self.sample_rate = sample_rate
        self.n_bins = n_bins
        self.learn_windows = learn_windows
        self.z_threshold = z_threshold
        self.z_score_scale = z_score_scale
        self.sigma_floor_db = sigma_floor_db
        self.occupancy_margin_db = occupancy_margin_db

        self.fitted = False
        self._buffer = []
        self._mean = None  # per-bin baseline mean (dB shape)
        self._std = None  # per-bin baseline std (floored)
        self._save_path = None  # if set, persist the baseline once learned

    def _featurize(self, iq: np.ndarray):
        """Window -> (normalized dB PSD-shape vector, raw psd). The vector is the
        baseline feature; the psd also yields the event metrics."""
        f, psd = welch_psd(iq, self.sample_rate, self.n_bins)
        order = np.argsort(f)  # stable low->high frequency layout
        psd_sorted = psd[order]
        db = 10.0 * np.log10(psd_sorted + 1e-12)
        feature = db - np.median(db)  # spectral shape, not absolute level
        return feature.astype(np.float64), psd

    def _fit(self) -> None:
        X = np.vstack(self._buffer)
        self._mean = X.mean(axis=0)
        self._std = np.maximum(X.std(axis=0), self.sigma_floor_db)
        self.fitted = True
        self._buffer = []  # free the learn buffer
        print(f"[anomaly] learn complete ({len(X)} windows); watching")
        if self._save_path:
            self.save(self._save_path)
            print(f"[anomaly] baseline saved to {self._save_path}")

    def save(self, path: str) -> None:
        """Persist the learned per-bin baseline (mean/std) so a run can reuse it."""
        np.savez(path, mean=self._mean, std=self._std)

    def load(self, path: str) -> None:
        """Load a saved baseline and go straight to watching (skip learning)."""
        data = np.load(path)
        self._mean = data["mean"]
        self._std = data["std"]
        self.fitted = True

    def evaluate(self, iq: np.ndarray) -> dict:
        feature, psd = self._featurize(iq)
        metrics = psd_metrics(psd, self.sample_rate, self.occupancy_margin_db)

        classification = classify_emitter(metrics["occupied_bw_hz"], metrics["flatness"], self.sample_rate)
        if not self.fitted:
            self._buffer.append(feature)
            if len(self._buffer) >= self.learn_windows:
                self._fit()
            return {"detected": False, "anomaly_score": 0.0, "classification": classification, **metrics}

        # Max excess of any bin above its learned baseline, in std units.
        max_z = float(np.max((feature - self._mean) / self._std))
        anomaly_score = min(max(max_z / self.z_score_scale, 0.0), 1.0)
        return {
            "detected": bool(max_z >= self.z_threshold),
            "anomaly_score": float(round(anomaly_score, 3)),
            "classification": classification,
            **metrics,
        }
