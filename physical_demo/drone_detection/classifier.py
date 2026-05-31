"""Case 3 — trained classifier + a bus source that runs it.

`RFClassifier` wraps a scikit-learn RandomForest over the feature vectors from
features.py (data-efficient, interpretable — see README on why not a CNN).
`ClassifierSource` captures a window-stack, classifies it, and pushes a detection
event to the bus for any non-background ("quiet") prediction — slotting in like
the other detection sources.
"""
import threading

import numpy as np

import config
from features import stack_features


class RFClassifier:
    def __init__(self, model=None) -> None:
        if model is None:
            from sklearn.ensemble import RandomForestClassifier

            model = RandomForestClassifier(n_estimators=200, random_state=0)
        self.model = model

    def fit(self, X, y) -> None:
        self.model.fit(np.asarray(X), list(y))

    def predict(self, vec) -> str:
        return str(self.model.predict(np.asarray(vec, dtype=float).reshape(1, -1))[0])

    def predict_conf(self, vec) -> float:
        """Max class probability for `vec` — used as the detection's anomaly_score."""
        proba = self.model.predict_proba(np.asarray(vec, dtype=float).reshape(1, -1))[0]
        return float(np.max(proba))

    def save(self, path: str) -> None:
        import joblib

        joblib.dump(self.model, path)

    @classmethod
    def load(cls, path: str) -> "RFClassifier":
        import joblib

        return cls(model=joblib.load(path))


class ClassifierSource:
    def __init__(
        self,
        capture,
        classifier,
        bus,
        sample_rate: float,
        center_freq_hz: int,
        stack_size: int = 8,
        quiet_label: str = "quiet",
        window_samples: int = config.WINDOW_SAMPLES,
        source_name: str = "classifier",
    ) -> None:
        self.capture = capture
        self.classifier = classifier
        self.bus = bus
        self.sample_rate = sample_rate
        self.center_freq_hz = center_freq_hz
        self.stack_size = stack_size
        self.quiet_label = quiet_label
        self.window_samples = window_samples
        self.source_name = source_name

    def step(self):
        """Capture a window-stack, classify it, push an event for a non-quiet label.
        Returns the predicted label, or None if the stream ended."""
        windows = []
        for _ in range(self.stack_size):
            w = self.capture.read_window(self.window_samples)
            if w.size == 0:
                return None
            windows.append(w)
        vec = stack_features(windows, self.sample_rate)
        label = self.classifier.predict(vec)
        if label != self.quiet_label:
            self.bus.publish({
                "source": self.source_name,
                "anomaly_score": float(round(self.classifier.predict_conf(vec), 3)),
                "classification": label,
                "label": label,
                "center_freq_hz": self.center_freq_hz,
                "snr_db": float(vec[2]),          # snr feature
                "occupied_bw_hz": int(vec[0]),    # occupied_bw feature
            })
        return label

    def run(self, stop_event: threading.Event) -> None:
        try:
            while not stop_event.is_set():
                if self.step() is None:
                    print("[classifier] stream ended; stopping")
                    break
        finally:
            self.capture.close()
