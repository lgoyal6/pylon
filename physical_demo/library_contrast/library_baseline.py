"""Library baseline — the Dedrone/DroneShield analog.

Implemented as **distance-based template matching**, not a soft-max classifier.
That matches how real signature libraries behave: each known emitter has a
stored fingerprint, and an input is "recognized" only when its features are
close enough to a known fingerprint. Novel emitters that look unlike anything
in the library trip the *no-match* path → no detection. That's exactly the
failure mode this experiment exposes.

A soft-max classifier (RandomForest etc.) is the wrong analog because it
*always* picks a class even for out-of-distribution input, which would let it
"catch" novel emitters by confidently misclassifying them.
"""
from __future__ import annotations

import numpy as np
from sklearn.neighbors import NearestNeighbors

import config

NO_MATCH = "no_match"


class LibraryBaseline:
    def __init__(
        self,
        no_match_distance_quantile: float = config.LIBRARY_MATCH_DISTANCE_QUANTILE,
        n_neighbors: int = 1,
    ) -> None:
        # Anything farther from its nearest training neighbor than this
        # quantile of intra-training distances is treated as unmatched.
        self.no_match_distance_quantile = no_match_distance_quantile
        self.n_neighbors = n_neighbors
        self._nn: NearestNeighbors | None = None
        self._y_train: np.ndarray | None = None
        self._match_threshold: float | None = None

    def fit(self, X: np.ndarray, y: np.ndarray) -> "LibraryBaseline":
        # Normalize features so distances aren't dominated by one big-scale dim.
        self._mu = X.mean(axis=0)
        self._sigma = X.std(axis=0) + 1e-6
        Xn = (X - self._mu) / self._sigma

        self._nn = NearestNeighbors(n_neighbors=self.n_neighbors + 1).fit(Xn)
        self._y_train = y.copy()

        # Set match threshold from intra-training nearest-neighbour distances.
        # (Skip the self-match at index 0.)
        dists, _ = self._nn.kneighbors(Xn, n_neighbors=2)
        self._match_threshold = float(
            np.quantile(dists[:, 1], self.no_match_distance_quantile)
        )
        return self

    def _ensure_fit(self) -> None:
        if self._nn is None or self._y_train is None or self._match_threshold is None:
            raise RuntimeError("fit() before predicting")

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Closest-class label, or ``no_match`` if too far from anything known."""
        self._ensure_fit()
        Xn = (X - self._mu) / self._sigma
        dists, idx = self._nn.kneighbors(Xn, n_neighbors=1)
        preds = self._y_train[idx.ravel()].astype(object)
        preds[dists.ravel() > self._match_threshold] = NO_MATCH
        return preds

    @property
    def match_threshold(self) -> float:
        self._ensure_fit()
        return self._match_threshold  # type: ignore[return-value]

    def is_detection(self, X: np.ndarray) -> np.ndarray:
        """Binary "library recognized a non-ambient signature" decision.

        A miss = this returns False on a window that truly contains an emitter
        (whether known or novel). The novel emitter falls into ``no_match``
        because it doesn't resemble any stored fingerprint — that's the miss
        the anomaly detector recovers.
        """
        preds = self.predict(X)
        is_ambient = preds == config.AMBIENT_CLASS
        is_no_match = preds == NO_MATCH
        return ~(is_ambient | is_no_match)
