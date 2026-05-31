"""Software loopback: the emitter's own waveforms -> the detector's classifier.

No SDR/hardware. Builds each beacon waveform exactly as the emitter CLI would
(via _build_waveform), adds receiver noise, and asserts the classifier labels it
correctly. This is the end-to-end check that the transmitter's "jamming-like"
modes actually read as jamming-like to the detector.
"""
import types

import numpy as np

import config
from beacon import _build_waveform
from detector import classify_emitter, psd_metrics, welch_psd

FS = 2_000_000      # the beacon's default sample rate
N = 2 ** 15         # the beacon's default buffer length


def _emit(waveform: str) -> np.ndarray:
    """The exact IQ the emitter CLI would transmit for this waveform."""
    args = types.SimpleNamespace(
        waveform=waveform, sample_rate=FS, buffer=N,
        offset=200_000, bw=300_000, duty=1.0,
    )
    return _build_waveform(args)


def _classify_received(waveform: np.ndarray, noise_amp: float = 0.05, seed: int = 0) -> str:
    """Emitter waveform + receiver noise -> classifier label (what a node would emit)."""
    rng = np.random.default_rng(seed)
    noise = (rng.standard_normal(N) + 1j * rng.standard_normal(N)).astype(np.complex64) * noise_amp
    _, psd = welch_psd(waveform + noise, FS, config.N_FEATURE_BINS)
    m = psd_metrics(psd, FS, config.OCCUPANCY_MARGIN_DB)
    return classify_emitter(m["occupied_bw_hz"], m["flatness"], FS)


def test_tone_emitter_reads_as_comms_like():
    assert _classify_received(_emit("tone")) == "comms-like"


def test_barrage_emitter_reads_as_jamming_like():
    assert _classify_received(_emit("barrage")) == "jamming-like"


def test_sweep_emitter_reads_as_jamming_like():
    assert _classify_received(_emit("sweep")) == "jamming-like"
