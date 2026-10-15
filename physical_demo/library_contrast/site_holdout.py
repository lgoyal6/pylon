"""Split captures before window expansion to prevent evaluation leakage.
recordings.py uses the partition check for sessions, bytes and holdout axes.
Reject duplicate recordings and shared acquisition groups across partitions.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping


def validate_partitions(partitions, disjoint=("session_id", "sha256")) -> None:
    """Reject shared acquisition sessions or bytes before expanding windows.

    A receiver/site split alone is insufficient when two receivers observe the
    same transmission. Required metadata must be present in every partition.
    """
    owners = {key: {} for key in disjoint}
    for partition, rows in partitions.items():
        if not rows:
            raise ValueError(f"empty partition: {partition}")
        for row in rows:
            for key in disjoint:
                value = row.get(key)
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"missing {key} in {partition}")
                previous = owners[key].setdefault(value, partition)
                if previous != partition:
                    raise ValueError(f"{key} leakage between {previous} and {partition}")


def split_by_site(
    captures: Iterable[Mapping[str, str]], held_out_site: str
) -> tuple[list[Mapping[str, str]], list[Mapping[str, str]]]:
    rows = list(captures)
    if not held_out_site:
        raise ValueError("held_out_site must be non-empty")
    if not rows:
        raise ValueError("capture manifest is empty")

    sites: set[str] = set()
    seen_recordings: set[str] = set()
    for row in rows:
        missing = [key for key in ("recording_id", "site_id", "device_id", "day")
                   if not isinstance(row.get(key), str) or not row[key].strip()]
        if missing:
            raise ValueError(f"capture row missing required metadata: {', '.join(missing)}")
        recording = row["recording_id"]
        site = row["site_id"]
        if recording in seen_recordings:
            raise ValueError(f"duplicate recording_id: {recording}")
        seen_recordings.add(recording)
        sites.add(site)

    if held_out_site not in sites:
        raise ValueError(f"held-out site not found: {held_out_site}")
    train = [row for row in rows if row["site_id"] != held_out_site]
    test = [row for row in rows if row["site_id"] == held_out_site]
    if not train:
        raise ValueError("site holdout leaves no training captures")

    # Older manifests lack these fields. If supplied, they must be complete
    # and disjoint; the stricter study loader always requires both.
    keys = tuple(key for key in ("session_id", "sha256") if any(key in r for r in rows))
    if keys:
        validate_partitions({"train": train, "test": test}, disjoint=keys)
    return train, test
