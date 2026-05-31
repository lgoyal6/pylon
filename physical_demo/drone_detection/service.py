"""FastAPI detection service (port 5001).

Exposes the binary detection state at ``GET /status`` and a manual control
endpoint ``POST /sim`` (the Iteration 0 stub "detector"). A background task
re-publishes the detection event to multicast while detected, so the relay sees
a live stream rather than a single edge.
"""
import asyncio
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel

import config
from publisher import MulticastPublisher, build_event
from state import DetectionState

state = DetectionState()
publisher = MulticastPublisher()

# Optional hands-free demo toggling; set by main.py before launch (0 = off).
auto_toggle_s = 0.0

# Capture source + tuning, set by main.py before launch.
#   "sim"  -> manual /sim only (Iteration 0 behavior / stage fallback)
#   "live" -> RTL-SDR capture loop drives detection (Iteration 1)
source = "sim"
center_freq_hz = config.DEFAULT_CENTER_FREQ_HZ
sample_rate_hz = config.SAMPLE_RATE_HZ
gain = config.GAIN

# Which SDR backend the live loop uses, set by main.py.
#   "rtl"   -> NESDR/RTL via the rtl_sdr CLI (<=1.75 GHz)
#   "pluto" -> ADALM-Pluto via pyadi-iio (reaches 2.4 GHz)
sdr_kind = "rtl"

# Detector for the live loop, set by main.py.
#   "anomaly" -> open-world anomaly detector (Iteration 2, the product)
#   "energy"  -> occupied-bandwidth energy threshold (Iteration 1, contrast/legacy)
detector_kind = "anomaly"
learn_seconds = config.LEARN_SECONDS
load_model_path = None
save_model_path = None


class DetectorRunner:
    """Capture -> detect -> DetectionState loop. `capture` is injected so the
    logic is testable with a fake; live runs pass an RtlCapture."""

    def __init__(
        self,
        capture,
        detector,
        state: DetectionState,
        publisher: MulticastPublisher,
        center_freq_hz: int,
        debounce_on: int = config.DEBOUNCE_ON,
        debounce_off: int = config.DEBOUNCE_OFF,
        window_samples: int = config.WINDOW_SAMPLES,
    ) -> None:
        self.capture = capture
        self.detector = detector
        self.state = state
        self.publisher = publisher
        self.center_freq_hz = center_freq_hz
        self.debounce_on = debounce_on  # consecutive detections to flip on (fast)
        self.debounce_off = debounce_off  # consecutive misses to clear (hangover)
        self.window_samples = window_samples
        self._on = 0
        self._off = 0

    def step(self):
        """Process one window; apply debounced state changes; publish edges.
        Returns the detector result, or None if the capture stream ended."""
        iq = self.capture.read_window(self.window_samples)
        if iq.size == 0:  # stream ended (e.g. no device)
            return None
        result = self.detector.evaluate(iq)
        if result["detected"]:
            self._on += 1
            self._off = 0
            if self._on >= self.debounce_on:
                rising = self.state.set_detected(
                    result["anomaly_score"],
                    center_freq_hz=self.center_freq_hz,
                    snr_db=result["snr_db"],
                    occupied_bw_hz=result["occupied_bw_hz"],
                    classification=result.get("classification"),
                )
                if rising:
                    self.publisher.send(build_event(self.state.event_snapshot()))
        else:
            self._off += 1
            self._on = 0
            if self._off >= self.debounce_off:
                self.state.clear()
        return result

    def run(self, stop_event: threading.Event) -> None:
        try:
            while not stop_event.is_set():
                if self.step() is None:
                    print("[capture] stream ended (no device?); detector loop stopping")
                    break
        finally:
            self.capture.close()


class SimRequest(BaseModel):
    detected: bool
    anomaly_score: float | None = None


def _publish_current() -> None:
    """Publish a detection event from the current state. Uses event_snapshot so
    real RF metrics are sent when present (stubs only fall back via build_event)."""
    publisher.send(build_event(state.event_snapshot()))


def _toggle() -> None:
    """Flip detection state once; publish on the rising edge."""
    if state.detected:
        state.clear()
    elif state.set_detected(config.DEFAULT_ANOMALY_SCORE):
        _publish_current()


async def _heartbeat() -> None:
    while True:
        await asyncio.sleep(config.PUBLISH_INTERVAL_S)
        if state.detected:
            _publish_current()


async def _auto_toggle() -> None:
    while True:
        await asyncio.sleep(auto_toggle_s)
        _toggle()


def _start_capture_thread():
    """Build the RTL capture loop and run it in a daemon thread. Returns
    (stop_event, thread) or None if hardware/import fails (falls back to sim)."""
    # imported lazily: only the live path needs librtlsdr / libiio
    if sdr_kind == "pluto":
        from capture import PlutoCapture

        capture = PlutoCapture(center_freq_hz=center_freq_hz, sample_rate=sample_rate_hz, gain=gain)
    else:
        from capture import RtlCapture

        capture = RtlCapture(center_freq_hz=center_freq_hz, sample_rate=sample_rate_hz, gain=gain)
    if detector_kind == "energy":
        from detector import EnergyThresholdDetector
        detector = EnergyThresholdDetector(sample_rate=sample_rate_hz)
    else:
        from anomaly import AnomalyDetector
        learn_windows = max(1, int(learn_seconds * sample_rate_hz / config.WINDOW_SAMPLES))
        detector = AnomalyDetector(sample_rate=sample_rate_hz, learn_windows=learn_windows)
        if load_model_path:
            detector.load(load_model_path)
            print(f"[anomaly] loaded baseline from {load_model_path}; watching")
        elif save_model_path:
            detector._save_path = save_model_path  # _fit() persists when learning completes
        if not load_model_path:
            print(f"[anomaly] learning ambient for ~{learn_seconds:.0f}s ({learn_windows} windows); keep the target OFF")
    runner = DetectorRunner(capture, detector, state, publisher, center_freq_hz=center_freq_hz)
    stop_event = threading.Event()
    thread = threading.Thread(target=runner.run, args=(stop_event,), daemon=True)
    thread.start()
    return stop_event, thread


@asynccontextmanager
async def lifespan(app: FastAPI):
    tasks = [asyncio.create_task(_heartbeat())]
    if auto_toggle_s > 0:
        tasks.append(asyncio.create_task(_auto_toggle()))

    capture_handle = None
    if source == "live":
        try:
            capture_handle = _start_capture_thread()
        except Exception as exc:  # hardware/driver failure -> degrade to sim
            print(f"[capture] live source unavailable, falling back to /sim: {exc}")

    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        if capture_handle is not None:
            stop_event, thread = capture_handle
            stop_event.set()
            thread.join(timeout=2.0)
        publisher.close()


app = FastAPI(title="Drone Detection Service", lifespan=lifespan)


@app.get("/status")
async def status() -> dict:
    return state.snapshot()


@app.post("/sim")
async def sim(req: SimRequest) -> dict:
    """Stub detector control: flip the detection state by hand."""
    if req.detected:
        score = req.anomaly_score if req.anomaly_score is not None else config.DEFAULT_ANOMALY_SCORE
        rising = state.set_detected(score)
        if rising:  # publish immediately on the false->true edge
            _publish_current()
    else:
        state.clear()
    return state.snapshot()
