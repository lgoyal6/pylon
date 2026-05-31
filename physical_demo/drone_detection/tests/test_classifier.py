"""RFClassifier (RandomForest on feature vectors) + ClassifierSource (bus source)."""
import numpy as np

import config
from bus import DetectionBus
from classifier import ClassifierSource, RFClassifier


def _two_clusters(seed=0):
    rng = np.random.default_rng(seed)
    X = np.vstack([rng.normal(0, 0.5, (20, 3)), rng.normal(10, 0.5, (20, 3))])
    y = ["quiet"] * 20 + ["hopper"] * 20
    return X, y


def test_fit_predict_separable_classes():
    clf = RFClassifier()
    clf.fit(*_two_clusters())
    assert clf.predict([0, 0, 0]) == "quiet"
    assert clf.predict([10, 10, 10]) == "hopper"


def test_predict_conf_in_unit_interval():
    clf = RFClassifier()
    clf.fit(*_two_clusters())
    c = clf.predict_conf([10, 10, 10])
    assert 0.0 <= c <= 1.0


def test_save_load_round_trip(tmp_path):
    clf = RFClassifier()
    clf.fit(*_two_clusters())
    path = str(tmp_path / "m.joblib")
    clf.save(path)
    loaded = RFClassifier.load(path)
    assert loaded.predict([10, 10, 10]) == "hopper"


# --- ClassifierSource -------------------------------------------------------

class _FakeModel:
    def __init__(self, label, conf=0.9):
        self._label, self._conf = label, conf

    def predict(self, vec):
        return self._label

    def predict_conf(self, vec):
        return self._conf


class _FakeCapture:
    def __init__(self, window):
        self._w = window

    def read_window(self, n):
        return self._w

    def close(self):
        pass


def _window():
    return np.zeros(config.WINDOW_SAMPLES, dtype=np.complex64)


def test_source_pushes_event_for_non_quiet_prediction():
    bus = DetectionBus()
    src = ClassifierSource(_FakeCapture(_window()), _FakeModel("hopper"), bus,
                           sample_rate=config.SAMPLE_RATE_HZ, center_freq_hz=2_437_000_000, stack_size=2)
    src.step()
    ev = bus.get(timeout=0.1)
    assert ev is not None
    assert ev["classification"] == "hopper"
    assert ev["source"] == "classifier"
    assert 0.0 <= ev["anomaly_score"] <= 1.0


def test_source_silent_on_quiet_prediction():
    bus = DetectionBus()
    src = ClassifierSource(_FakeCapture(_window()), _FakeModel("quiet"), bus,
                           sample_rate=config.SAMPLE_RATE_HZ, center_freq_hz=2_437_000_000, stack_size=2)
    src.step()
    assert bus.get(timeout=0.02) is None  # background class -> no detection event
