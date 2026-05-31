"""Single source of truth for the binary detection state.

`/status` reads it, the multicast publisher emits from it, and "the detector"
writes it. In Iteration 0 the detector was the `/sim` endpoint; in Iteration 1 a
capture+detect loop (a background thread) writes the same object — that seam
stays fixed.

Because a capture thread now mutates state while the event loop reads it, a
`threading.Lock` guards every read/write.
"""
import threading
from datetime import datetime, timezone


def iso_now() -> str:
    """UTC timestamp as ISO 8601 with millisecond precision and a 'Z' suffix."""
    dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


class DetectionState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.detected = False
        self.anomaly_score = 0.0
        self.since = None  # ISO timestamp of the rising edge, else None
        # Latest detection-event metrics (None until a real detector sets them).
        self.center_freq_hz = None
        self.snr_db = None
        self.occupied_bw_hz = None
        self.classification = None

    def set_detected(
        self,
        anomaly_score: float,
        *,
        center_freq_hz: int = None,
        snr_db: float = None,
        occupied_bw_hz: int = None,
        classification: str = None,
    ) -> bool:
        """Mark detected. Returns True if this was a rising edge (false->true).

        `since` is pinned to the rising edge; later calls only update the score
        and metrics.
        """
        with self._lock:
            rising = not self.detected
            if rising:
                self.since = iso_now()
            self.detected = True
            self.anomaly_score = anomaly_score
            self.center_freq_hz = center_freq_hz
            self.snr_db = snr_db
            self.occupied_bw_hz = occupied_bw_hz
            self.classification = classification
            return rising

    def clear(self) -> None:
        with self._lock:
            self.detected = False
            self.anomaly_score = 0.0
            self.since = None
            self.center_freq_hz = None
            self.snr_db = None
            self.occupied_bw_hz = None
            self.classification = None

    def snapshot(self) -> dict:
        """Status view consumed by GET /status (the fixed contract)."""
        with self._lock:
            return {
                "detected": self.detected,
                "anomaly_score": self.anomaly_score,
                "since": self.since,
            }

    def event_snapshot(self) -> dict:
        """Everything build_event needs: score + latest RF metrics."""
        with self._lock:
            return {
                "anomaly_score": self.anomaly_score,
                "center_freq_hz": self.center_freq_hz,
                "snr_db": self.snr_db,
                "occupied_bw_hz": self.occupied_bw_hz,
                "classification": self.classification,
            }
