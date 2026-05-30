"""Single source of truth for the binary detection state.

`/status` reads it, the multicast publisher emits from it, and "the detector"
writes it. In Iteration 0 the detector is the `/sim` control endpoint; in later
iterations a real capture loop writes the same object — that seam stays fixed.

All mutation happens on uvicorn's single event-loop thread with no `await`
between read and write, so the methods are synchronous and need no lock.
"""
from datetime import datetime, timezone


def iso_now() -> str:
    """UTC timestamp as ISO 8601 with millisecond precision and a 'Z' suffix."""
    dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


class DetectionState:
    def __init__(self) -> None:
        self.detected = False
        self.anomaly_score = 0.0
        self.since = None  # ISO timestamp of the rising edge, else None

    def set_detected(self, anomaly_score: float) -> bool:
        """Mark detected. Returns True if this was a rising edge (false->true).

        `since` is pinned to the rising edge; later calls only update the score.
        """
        rising = not self.detected
        if rising:
            self.since = iso_now()
        self.detected = True
        self.anomaly_score = anomaly_score
        return rising

    def clear(self) -> None:
        self.detected = False
        self.anomaly_score = 0.0
        self.since = None

    def snapshot(self) -> dict:
        return {
            "detected": self.detected,
            "anomaly_score": self.anomaly_score,
            "since": self.since,
        }
