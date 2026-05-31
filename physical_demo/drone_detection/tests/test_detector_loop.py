import json

import numpy as np
import pytest

import config
import service
from detector import EnergyThresholdDetector

FS = config.SAMPLE_RATE_HZ
N = config.WINDOW_SAMPLES


@pytest.fixture(autouse=True)
def reset_state():
    service.state.clear()


def _noise(seed):
    rng = np.random.default_rng(seed)
    return (rng.standard_normal(N) + 1j * rng.standard_normal(N)).astype(np.complex64)


def _noise_plus_signal(seed):
    """Band-limited ~200 kHz signal in noise — models a real wideband emitter."""
    rng = np.random.default_rng(seed)
    x = rng.standard_normal(N) + 1j * rng.standard_normal(N)
    X = np.fft.fft(x)
    freqs = np.fft.fftfreq(N, 1 / FS)
    X[np.abs(freqs - 200_000) > 100_000] = 0
    y = np.fft.ifft(X)
    y = y / np.sqrt(np.mean(np.abs(y) ** 2)) * 6.0
    return (y + _noise(seed + 1)).astype(np.complex64)


class FakeCapture:
    """Returns a fixed list of pre-built IQ windows, repeating the last one."""

    def __init__(self, windows):
        self.windows = windows
        self.i = 0

    def read_window(self, n):
        w = self.windows[min(self.i, len(self.windows) - 1)]
        self.i += 1
        return w

    def close(self):
        pass


def _runner(windows, debounce_on, debounce_off=10):
    cap = FakeCapture(windows)
    det = EnergyThresholdDetector(sample_rate=FS)
    return service.DetectorRunner(
        cap, det, service.state, service.publisher,
        center_freq_hz=433_000_000, debounce_on=debounce_on, debounce_off=debounce_off,
    )


def test_runner_stays_false_on_pure_noise():
    runner = _runner([_noise(s) for s in range(5)], debounce_on=3)
    for _ in range(5):
        runner.step()
    assert service.state.snapshot()["detected"] is False


def test_runner_needs_debounce_on_windows_before_flipping_on():
    runner = _runner([_noise_plus_signal(s) for s in range(5)], debounce_on=3)
    runner.step()
    runner.step()
    assert service.state.snapshot()["detected"] is False  # only 2 < debounce_on
    runner.step()
    assert service.state.snapshot()["detected"] is True  # 3rd consecutive flips it


def test_hangover_holds_detection_through_short_gap():
    # debounce_off acts as a hangover: brief non-detection doesn't clear at once.
    seq = [_noise_plus_signal(0)] + [_noise(100 + s) for s in range(3)]
    runner = _runner(seq, debounce_on=1, debounce_off=3)
    runner.step()  # signal -> detected
    assert service.state.snapshot()["detected"] is True
    runner.step()  # 1st quiet window: off=1 < 3 -> still held
    assert service.state.snapshot()["detected"] is True
    runner.step()  # off=2 < 3 -> still held
    assert service.state.snapshot()["detected"] is True
    runner.step()  # off=3 >= 3 -> clears
    assert service.state.snapshot()["detected"] is False


def test_publish_current_carries_real_metrics_when_detected(multicast_listener):
    # Regression: heartbeat/sim publishes must use event_snapshot (real metrics),
    # not the status snapshot (which would leak the config stub values).
    service.state.set_detected(0.5, center_freq_hz=94_100_000, snr_db=20.0, occupied_bw_hz=180_000)
    listener = multicast_listener()
    service._publish_current()
    event = json.loads(listener.recvfrom(65535)[0])
    assert event["center_freq_hz"] == 94_100_000
    assert event["snr_db"] == 20.0
    assert event["occupied_bw_hz"] == 180_000


def test_anomaly_detector_in_loop_learns_then_flips_on_novel():
    from anomaly import AnomalyDetector

    learn = 20
    det = AnomalyDetector(sample_rate=FS, n_bins=256, learn_windows=learn)
    windows = [_noise(s) for s in range(learn)] + [_noise_plus_signal(900)]
    cap = FakeCapture(windows)
    runner = service.DetectorRunner(
        cap, det, service.state, service.publisher,
        center_freq_hz=433_000_000, debounce_on=1, debounce_off=10,
    )
    for _ in range(learn):  # learn phase stays quiet
        runner.step()
        assert service.state.snapshot()["detected"] is False
    assert det.fitted is True
    runner.step()  # novel window -> flips
    assert service.state.snapshot()["detected"] is True


def test_runner_publishes_real_metrics_on_rising_edge(multicast_listener):
    listener = multicast_listener()
    runner = _runner([_noise_plus_signal(s) for s in range(5)], debounce_on=1)
    runner.step()
    event = json.loads(listener.recvfrom(65535)[0])
    assert event["center_freq_hz"] == 433_000_000
    assert event["occupied_bw_hz"] >= runner.detector.min_occupied_bw_hz


def test_runner_publishes_classification_on_rising_edge(multicast_listener):
    listener = multicast_listener()
    runner = _runner([_noise_plus_signal(s) for s in range(5)], debounce_on=1)
    runner.step()
    event = json.loads(listener.recvfrom(65535)[0])
    assert event["classification"] in ("comms-like", "jamming-like")
