"""Decoupling buffer between detection sources and the mesh sink.

Any detection method — SDR anomaly/classifier, BT scanner, etc. — pushes a
standardized detection event onto the bus and knows nothing about the mesh. A
single sink (see service.drain_bus) drains it to /status + the mesh. This lets
detection methods be swapped or combined without touching the publishing path.

A detection event is a plain dict. Conventionally:
    {"source": "<name>", "anomaly_score": float, "center_freq_hz": int,
     "snr_db": float, "occupied_bw_hz": int, "classification": str,
     "label": str|None, "cleared": bool}     # cleared=True => detection ended
"""
import queue


class DetectionBus:
    def __init__(self, maxsize: int = 1000) -> None:
        self._q: "queue.Queue[dict]" = queue.Queue(maxsize=maxsize)

    def publish(self, event: dict) -> None:
        """Push a detection event. Non-blocking: drops if full (real-time data —
        a stalled source is worse than a dropped stale event)."""
        try:
            self._q.put_nowait(event)
        except queue.Full:
            pass

    def get(self, timeout: float = None):
        """Pop the next event, or None if none arrives within `timeout` seconds."""
        try:
            return self._q.get(timeout=timeout)
        except queue.Empty:
            return None

    def __len__(self) -> int:
        return self._q.qsize()
