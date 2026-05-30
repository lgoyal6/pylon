"""Open-world anomaly detector — what the detection service runs at Iter 2.

Unsupervised IsolationForest trained on ambient windows only. At inference
time, anything that doesn't fit the ambient distribution scores high — known
or novel, the model doesn't care. That's the wedge: it catches the novel
emitter the library missed, because "different from ambient" is enough.
"""
from __future__ import annotations

import numpy as np
from sklearn.ensemble import IsolationForest

import config


class AnomalyDetector:
    def __init__(
        self,
        threshold_quantile: float = config.ANOMALY_THRESHOLD_QUANTILE,
        random_state: int = config.RANDOM_SEED,
    ) -> None:
        self.threshold_quantile = threshold_quantile
        # contamination='auto' avoids assuming a specific outlier fraction in
        # the training (ambient-only) data.
        self.model = IsolationForest(
            n_estimators=200,
            contamination="auto",
            random_state=random_state,
            n_jobs=-1,
        )
        self._threshold: float | None = None

    def fit(self, X_ambient: np.ndarray) -> "AnomalyDetector":
        """Learn phase: fit the model and pick a threshold from ambient scores."""
        self.model.fit(X_ambient)
        ambient_scores = self.score(X_ambient)
        # Threshold at the quantile of ambient scores — calibrated so the
        # ambient false-positive rate is roughly (1 - quantile).
        self._threshold = float(np.quantile(ambient_scores, self.threshold_quantile))
        return self

    def score(self, X: np.ndarray) -> np.ndarray:
        """Higher score = more anomalous. (Inverts IsolationForest's convention.)"""
        # decision_function: higher = more "inlier". Negate to make higher = anomalous.
        return -self.model.decision_function(X)

    @property
    def threshold(self) -> float:
        if self._threshold is None:
            raise RuntimeError("fit() before reading threshold")
        return self._threshold

    def is_detection(self, X: np.ndarray) -> np.ndarray:
        """Binary "this looks unlike ambient" decision."""
        return self.score(X) > self.threshold
