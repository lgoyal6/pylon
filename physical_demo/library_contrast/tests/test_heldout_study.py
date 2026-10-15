"""Check calibration budgets and reconstruction in heldout_study.py.
Use test_recordings.py fixtures to run every detector arm on isolated groups.
Reject changed protocols and preserve conservative threshold tie handling.
"""
import hashlib
import json

import numpy as np
import pytest

from heldout_study import budget_threshold, relative_power, run, summarize, source_hashes
from test_recordings import write_manifest


def test_calibration_budget_and_ties_are_conservative():
    scores = np.array([0, 1, 2, 2, 3.])
    threshold = budget_threshold(scores, 3600, 2)
    assert threshold == 2
    assert (scores > threshold).sum() == 1
    assert (scores > budget_threshold(scores, 3600, 0)).sum() == 0


@pytest.mark.parametrize("scores,seconds,budget", [([], 1, 1), ([np.nan], 1, 1), ([1], 0, 1), ([1], 1, -1)])
def test_invalid_calibration_rejected(scores, seconds, budget):
    with pytest.raises(ValueError):
        budget_threshold(np.array(scores), seconds, budget)


def test_relative_power_removes_a_uniform_gain_shift():
    X = np.random.default_rng(1).normal(size=(3, 69))
    shifted = X.copy()
    shifted[:, :64] += 2
    shifted[:, 66] += 2
    np.testing.assert_allclose(relative_power(shifted), relative_power(X), atol=1e-12)


def test_study_rebuilds_from_raw_and_refuses_protocol_mutation(tmp_path):
    manifest, _ = write_manifest(tmp_path)
    protocol = tmp_path / "protocol.json"
    protocol.write_text(json.dumps(dict(manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
                                        source_sha256=source_hashes(),
                                        window_samples=1024, hop_samples=1024,
                                        seed=1337, false_alerted_windows_per_hour=100)))
    output = tmp_path / "result.json"
    result = run(manifest, protocol, output)
    assert result["summary"] == summarize(result["raw"], 1337)
    assert len(result["summary"]) == 5
    assert result["calibration"]["library_budget"]["false_alerted_windows_per_hour"] <= 100
    with pytest.raises(ValueError, match="output already exists"):
        run(manifest, protocol, output)
    manifest.write_text(manifest.read_text() + "\n")
    with pytest.raises(ValueError, match="does not bind"):
        run(manifest, protocol, tmp_path / "other.json")


def test_source_mutation_requires_a_new_protocol(tmp_path):
    manifest, _ = write_manifest(tmp_path)
    protocol = tmp_path / "protocol.json"
    protocol.write_text(json.dumps({"source_sha256": {"different.py": "old"}}))
    with pytest.raises(ValueError, match="source hashes differ"):
        run(manifest, protocol, tmp_path / "result.json")
