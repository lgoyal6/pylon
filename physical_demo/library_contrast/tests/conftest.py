"""Shared pytest setup — short captures keep tests fast."""
from __future__ import annotations

import numpy as np
import pytest

import config

# Tests use much shorter captures than the demo run so the suite stays snappy.
TEST_DURATION_S = 0.25


@pytest.fixture(scope="session")
def rng() -> np.random.Generator:
    return np.random.default_rng(config.RANDOM_SEED)


@pytest.fixture(scope="session")
def short_duration() -> float:
    return TEST_DURATION_S
