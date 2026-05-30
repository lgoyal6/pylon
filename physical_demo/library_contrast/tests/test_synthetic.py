from __future__ import annotations

import numpy as np
import pytest

import config
import synthetic


def test_generate_all_classes_have_expected_sample_count(short_duration):
    expected = int(short_duration * config.SAMPLE_RATE_HZ)
    for name in config.ALL_CLASSES:
        iq = synthetic.generate(name, duration_s=short_duration, seed=0)
        assert iq.shape == (expected,), f"{name}: wrong sample count"
        assert iq.dtype == np.complex64


def test_generate_unknown_class_raises():
    with pytest.raises(KeyError):
        synthetic.generate("not-a-real-class")


def test_generate_is_deterministic_for_same_seed(short_duration):
    a = synthetic.generate("lora", duration_s=short_duration, seed=7)
    b = synthetic.generate("lora", duration_s=short_duration, seed=7)
    np.testing.assert_array_equal(a, b)


def test_different_seeds_produce_different_iq(short_duration):
    a = synthetic.generate("wifi", duration_s=short_duration, seed=1)
    b = synthetic.generate("wifi", duration_s=short_duration, seed=2)
    assert not np.array_equal(a, b)


def test_generate_all_returns_every_class(short_duration):
    captures = synthetic.generate_all(duration_s=short_duration)
    assert set(captures.keys()) == set(config.ALL_CLASSES)
    for name, iq in captures.items():
        assert iq.size > 0, f"empty capture for {name}"
