"""Learn ambient spectral shape and flag per-bin RF deviations.
service.DetectorRunner consumes the same interface as energy detection.
Normalize in float64 to preserve centering across FFT implementations.
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
        baseline: str = "zscore",  # "zscore" (mean/std) or "quantile" (robust for bursty bands)
        quantile: float = config.QUANTILE_Q,
        quantile_margin_db: float = config.QUANTILE_MARGIN_DB,
        quantile_score_scale_db: float = config.QUANTILE_SCORE_SCALE_DB,
    ) -> None:
        self.sample_rate = sample_rate
        self.n_bins = n_bins
        self.learn_windows = learn_windows
        self.z_threshold = z_threshold
        self.z_score_scale = z_score_scale
        self.sigma_floor_db = sigma_floor_db
        self.occupancy_margin_db = occupancy_margin_db
        self.baseline = baseline
        self.quantile = quantile
        self.quantile_margin_db = quantile_margin_db
        self.quantile_score_scale_db = quantile_score_scale_db

        self.fitted = False
        self._buffer = []
        self._mean = None  # per-bin baseline mean (dB shape) - zscore
        self._std = None  # per-bin baseline std (floored) - zscore
        self._ceiling = None  # per-bin learned high-percentile ceiling - quantile
        self._save_path = None  # if set, persist the baseline once learned

    def _featurize(self, iq: np.ndarray):
        """Window -> (normalized dB PSD-shape vector, raw psd). The vector is the
        baseline feature; the psd also yields the event metrics."""
        f, psd = welch_psd(iq, self.sample_rate, self.n_bins)
        order = np.argsort(f)  # stable low->high frequency layout
        psd_sorted = psd[order].astype(np.float64)
        db = 10.0 * np.log10(psd_sorted + 1e-12)
        feature = db - np.median(db)  # spectral shape, not absolute level
        return feature, psd

    def _fit(self) -> None:
        X = np.vstack(self._buffer)
        if self.baseline == "quantile":
            self._ceiling = np.quantile(X, self.quantile, axis=0)
        else:
            self._mean = X.mean(axis=0)
            self._std = np.maximum(X.std(axis=0), self.sigma_floor_db)
        self.fitted = True
        self._buffer = []  # free the learn buffer
        print(f"[anomaly] learn complete ({len(X)} windows, baseline={self.baseline}); watching")
        if self._save_path:
            self.save(self._save_path)
            print(f"[anomaly] baseline saved to {self._save_path}")

    def _score(self, feature: np.ndarray):
        """(detected, anomaly_score) for a featurized window under the chosen baseline."""
        if self.baseline == "quantile":
            # Greatest excess (dB) of any bin above its learned 'normal-busy' ceiling.
            excess = float(np.max(feature - self._ceiling))
            score = min(max(excess / self.quantile_score_scale_db, 0.0), 1.0)
            return bool(excess >= self.quantile_margin_db), score
        max_z = float(np.max((feature - self._mean) / self._std))
        score = min(max(max_z / self.z_score_scale, 0.0), 1.0)
        return bool(max_z >= self.z_threshold), score

    def save(self, path: str) -> None:
        """Persist the learned per-bin baseline so a run can reuse it."""
        if self.baseline == "quantile":
            np.savez(path, ceiling=self._ceiling)
        else:
            np.savez(path, mean=self._mean, std=self._std)

    def load(self, path: str) -> None:
        """Load a saved baseline and go straight to watching (skip learning)."""
        data = np.load(path)
        if "ceiling" in data:
            self._ceiling = data["ceiling"]
            self.baseline = "quantile"
        else:
            self._mean = data["mean"]
            self._std = data["std"]
            self.baseline = "zscore"
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

        detected, anomaly_score = self._score(feature)
        return {
            "detected": detected,
            "anomaly_score": float(round(anomaly_score, 3)),
            "classification": classification,
            **metrics,
        }
