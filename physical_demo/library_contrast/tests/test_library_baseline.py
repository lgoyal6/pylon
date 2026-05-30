from __future__ import annotations

import numpy as np

import config
import features
import synthetic
from library_baseline import NO_MATCH, LibraryBaseline


def _features_for(class_names, duration_s, seed_base=0):
    X_parts, y_parts = [], []
    for i, name in enumerate(class_names):
        iq = synthetic.generate(name, duration_s=duration_s, seed=seed_base + i)
        X = features.iq_to_features(iq)
        X_parts.append(X)
        y_parts.append(np.full(X.shape[0], name, dtype=object))
    return np.concatenate(X_parts), np.concatenate(y_parts)


def test_fit_and_predict_known_classes(short_duration):
    """On the training distribution, the library should recognize its own classes."""
    classes = (config.AMBIENT_CLASS, *config.KNOWN_EMITTER_CLASSES)
    X, y = _features_for(classes, duration_s=short_duration)
    lib = LibraryBaseline().fit(X, y)
    preds = lib.predict(X)
    # Held-in accuracy should be high — the library should match its own training points.
    matched = preds != NO_MATCH
    correct = (preds == y) & matched
    assert matched.mean() > 0.8, f"too many self-rejections: {matched.mean():.0%}"
    assert correct.mean() > 0.85, f"low self-accuracy: {correct.mean():.0%}"


def test_no_match_threshold_rejects_far_points(short_duration):
    """A tight match distance should reject inputs far from any training point."""
    classes = (config.AMBIENT_CLASS, *config.KNOWN_EMITTER_CLASSES)
    X, y = _features_for(classes, duration_s=short_duration)
    lib = LibraryBaseline(no_match_distance_quantile=0.95).fit(X, y)

    # Construct features that are obviously far from training: large constant offset.
    far = X[:5].copy() + 100.0
    preds = lib.predict(far)
    assert (preds == NO_MATCH).all()


def test_novel_emitter_is_largely_missed(short_duration):
    """The headline behaviour: novel doesn't resemble any stored fingerprint."""
    classes = (config.AMBIENT_CLASS, *config.KNOWN_EMITTER_CLASSES)
    X_train, y_train = _features_for(classes, duration_s=short_duration)
    lib = LibraryBaseline().fit(X_train, y_train)

    novel_iq = synthetic.generate(config.NOVEL_CLASS, duration_s=short_duration, seed=99)
    X_novel = features.iq_to_features(novel_iq)
    detected = lib.is_detection(X_novel)
    # Most novel windows should fall into NO_MATCH and thus not be flagged as detections.
    assert detected.mean() < 0.5, f"library detected {detected.mean():.0%} of novel windows"


def test_match_threshold_is_finite_after_fit(short_duration):
    classes = (config.AMBIENT_CLASS, *config.KNOWN_EMITTER_CLASSES)
    X, y = _features_for(classes, duration_s=short_duration)
    lib = LibraryBaseline().fit(X, y)
    assert np.isfinite(lib.match_threshold) and lib.match_threshold > 0
