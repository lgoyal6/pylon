"""Check recording and acquisition-group separation before windowing.
Exercise site_holdout.py with disjoint groups and planted leakage.
Keep valid controls alongside duplicate and missing-metadata rejection.
"""
from __future__ import annotations

import pytest

from site_holdout import split_by_site, validate_partitions


def capture(recording_id: str, site_id: str, device_id: str = "rx-1") -> dict[str, str]:
    return {"recording_id": recording_id, "site_id": site_id, "device_id": device_id, "day": "2026-10-01"}


def test_site_holdout_keeps_recordings_and_sites_disjoint():
    train, test = split_by_site([capture("a", "north"), capture("b", "north", "rx-2"), capture("c", "south")], "south")
    assert {row["site_id"] for row in train} == {"north"}
    assert {row["site_id"] for row in test} == {"south"}
    assert {row["recording_id"] for row in train}.isdisjoint({row["recording_id"] for row in test})


def test_duplicate_recording_is_rejected_before_window_expansion():
    with pytest.raises(ValueError, match="duplicate recording_id"):
        split_by_site([capture("same", "north"), capture("same", "south")], "south")


def test_missing_device_metadata_is_rejected():
    row = capture("a", "north")
    row["device_id"] = ""
    with pytest.raises(ValueError, match="device_id"):
        split_by_site([row, capture("b", "south")], "south")


def test_holdout_must_leave_training_data():
    with pytest.raises(ValueError, match="no training captures"):
        split_by_site([capture("a", "north")], "north")


@pytest.mark.parametrize("key", ["session_id", "sha256"])
def test_same_session_or_renamed_content_is_rejected(key):
    rows = [capture("a", "north"), capture("b", "south")]
    for row in rows:
        row[key] = "same"
    with pytest.raises(ValueError, match=f"{key} leakage"):
        split_by_site(rows, "south")


def test_partition_oracle_accepts_separate_sessions_and_bytes():
    validate_partitions({"train": [{"session_id": "s1", "sha256": "h1"}],
                         "calibration": [{"session_id": "s2", "sha256": "h2"}],
                         "test": [{"session_id": "s3", "sha256": "h3"}]})


def test_partition_oracle_rejects_missing_lineage():
    with pytest.raises(ValueError, match="missing session_id"):
        validate_partitions({"train": [{"sha256": "h1"}]})


@pytest.mark.parametrize("value", [" ", None, 123])
def test_invalid_metadata_is_rejected(value):
    row = capture("a", "north")
    row["day"] = value
    with pytest.raises(ValueError, match="day"):
        split_by_site([row, capture("b", "south")], "south")
