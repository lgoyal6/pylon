from __future__ import annotations

import numpy as np

import config
import features
import synthetic
from anomaly_detector import AnomalyDetector


def test_fit_sets_threshold(short_duration):
    iq = synthetic.generate(config.AMBIENT_CLASS, duration_s=short_duration, seed=0)
    X = features.iq_to_features(iq)
    det = AnomalyDetector().fit(X)
    assert isinstance(det.threshold, float)


def test_ambient_false_positive_rate_is_low(short_duration):
    iq = synthetic.generate(config.AMBIENT_CLASS, duration_s=short_duration, seed=0)
    X = features.iq_to_features(iq)
    det = AnomalyDetector().fit(X)
    fp_rate = det.is_detection(X).mean()
    # Threshold is the 95th percentile of training scores by default, so
    # we'd expect ~5% FP rate on training data itself.
    assert fp_rate < 0.20


def test_emitter_scores_higher_than_ambient(short_duration):
    amb_iq = synthetic.generate(config.AMBIENT_CLASS, duration_s=short_duration, seed=0)
    X_amb = features.iq_to_features(amb_iq)
    det = AnomalyDetector().fit(X_amb)

    for emitter in (*config.KNOWN_EMITTER_CLASSES, config.NOVEL_CLASS):
        em_iq = synthetic.generate(emitter, duration_s=short_duration, seed=11)
        X_em = features.iq_to_features(em_iq)
        assert det.score(X_em).mean() > det.score(X_amb).mean(), (
            f"{emitter} mean score not above ambient"
        )


def test_novel_emitter_is_detected(short_duration):
    """The pitch direction: anomaly catches novel even though it never saw it."""
    amb_iq = synthetic.generate(config.AMBIENT_CLASS, duration_s=short_duration, seed=0)
    det = AnomalyDetector().fit(features.iq_to_features(amb_iq))
    novel_iq = synthetic.generate(config.NOVEL_CLASS, duration_s=short_duration, seed=99)
    detected = det.is_detection(features.iq_to_features(novel_iq))
    assert detected.mean() > 0.5, f"anomaly only flagged {detected.mean():.0%} of novel"
