"""Synthetic IQ generators.

One generator per emitter class. Each returns complex baseband IQ at
`SAMPLE_RATE_HZ`. The classes are designed to be spectrally distinct so the
library baseline can learn them — and so the held-out `novel` class is far
enough from all of them that the library reliably misses it.
"""
from __future__ import annotations

import numpy as np

import config


def _awgn(n: int, snr_db: float, rng: np.random.Generator) -> np.ndarray:
    """Complex AWGN with unit signal-power assumed (caller scales accordingly)."""
    noise_power = 10 ** (-snr_db / 10.0)
    sigma = np.sqrt(noise_power / 2.0)
    return (rng.normal(0, sigma, n) + 1j * rng.normal(0, sigma, n)).astype(np.complex64)


def _samples(duration_s: float, sample_rate: float) -> int:
    return int(duration_s * sample_rate)


def generate_ambient(duration_s: float, sample_rate: float, rng: np.random.Generator) -> np.ndarray:
    """Pure complex AWGN — what the room sounds like with nothing transmitting."""
    n = _samples(duration_s, sample_rate)
    # Use a known noise floor so SNR math elsewhere is meaningful.
    sigma = 0.1
    return (rng.normal(0, sigma, n) + 1j * rng.normal(0, sigma, n)).astype(np.complex64)


def generate_wifi(duration_s: float, sample_rate: float, snr_db: float, rng: np.random.Generator) -> np.ndarray:
    """Wideband OFDM-like bursts: ~half duty cycle, occupies most of the band."""
    n = _samples(duration_s, sample_rate)
    # Random complex symbols at the full sample rate = wideband flat-ish PSD.
    sig = (rng.normal(0, 1, n) + 1j * rng.normal(0, 1, n)).astype(np.complex64) / np.sqrt(2)
    # Burst gate: 50 ms on, 50 ms off.
    burst_len = int(0.05 * sample_rate)
    gate = np.zeros(n, dtype=np.float32)
    for start in range(0, n, 2 * burst_len):
        gate[start : start + burst_len] = 1.0
    sig *= gate
    return (sig + _awgn(n, snr_db, rng)).astype(np.complex64)


def generate_bluetooth(duration_s: float, sample_rate: float, snr_db: float, rng: np.random.Generator) -> np.ndarray:
    """Wider GFSK pulses (~1 MHz BW) hopping every slot.

    Modeled as a narrow noise burst rather than a pure tone so the spectrum
    has a clearly wider footprint than ExpressLRS's narrow-tone hops.
    """
    n = _samples(duration_s, sample_rate)
    sig = np.zeros(n, dtype=np.complex64)
    slot = int(625e-6 * sample_rate)
    nyq = sample_rate / 2.0
    t = np.arange(slot) / sample_rate
    # ~1 MHz wide noise burst around the hopped center frequency.
    hop_bw = 1_000_000.0
    for start in range(0, n - slot, slot):
        f_off = rng.uniform(-nyq * 0.85, nyq * 0.85)
        carrier = np.exp(2j * np.pi * f_off * t).astype(np.complex64)
        mod = (rng.normal(0, 1, slot) + 1j * rng.normal(0, 1, slot)).astype(np.complex64)
        # Quick lowpass via cumulative-window smoothing to band-limit the noise.
        kernel = max(1, int(sample_rate / hop_bw))
        smoothed = np.convolve(mod, np.ones(kernel, dtype=np.float32) / kernel, mode="same").astype(np.complex64)
        sig[start : start + slot] = carrier * smoothed
    return (sig + _awgn(n, snr_db, rng)).astype(np.complex64)


def generate_lora(duration_s: float, sample_rate: float, snr_db: float, rng: np.random.Generator) -> np.ndarray:
    """Fast chirp upsweeps that sweep the band fast enough to show per-window.

    Original 40 ms chirps were too slow to be visible in a 500 µs FFT window
    (looked like a narrow tone). 500 µs chirps mean each window sees most of
    a sweep — wide spread is the discriminator.
    """
    n = _samples(duration_s, sample_rate)
    sig = np.zeros(n, dtype=np.complex64)
    # Chirp period matched to the FFT window so each window sees ≥1 full sweep.
    chirp_len = int(500e-6 * sample_rate)
    nyq = sample_rate / 2.0
    t = np.arange(chirp_len) / sample_rate
    f0, f1 = -nyq * 0.8, nyq * 0.8
    k = (f1 - f0) / (chirp_len / sample_rate)
    chirp = np.exp(2j * np.pi * (f0 * t + 0.5 * k * t * t)).astype(np.complex64)
    # Back-to-back chirps (mostly continuous) so the wide-spectrum signature is dense.
    for start in range(0, n - chirp_len, chirp_len):
        sig[start : start + chirp_len] = chirp
    return (sig + _awgn(n, snr_db, rng)).astype(np.complex64)


def generate_expresslrs(duration_s: float, sample_rate: float, snr_db: float, rng: np.random.Generator) -> np.ndarray:
    """Very narrow CW tone hopping every ~2 ms — modern FPV control link shape.

    Tone is much narrower (single sinusoid) than the BT GFSK burst, so the
    two narrow-hopping classes separate cleanly in the spectrum.
    """
    n = _samples(duration_s, sample_rate)
    sig = np.zeros(n, dtype=np.complex64)
    dwell = int(0.002 * sample_rate)
    nyq = sample_rate / 2.0
    t = np.arange(dwell) / sample_rate
    for start in range(0, n - dwell, dwell):
        f_off = rng.uniform(-nyq * 0.7, nyq * 0.7)
        sig[start : start + dwell] = np.exp(2j * np.pi * f_off * t).astype(np.complex64)
    return (sig + _awgn(n, snr_db, rng)).astype(np.complex64)


def generate_novel(duration_s: float, sample_rate: float, snr_db: float, rng: np.random.Generator) -> np.ndarray:
    """Dual-tone CW: two steady narrow tones, no hopping, continuous.

    Designed to look unlike any training class — RF can't fit it to wifi
    (wideband), BT/ExpressLRS (hopping), or LoRa (chirp). This is the
    "unknown adversary drone" stand-in.
    """
    n = _samples(duration_s, sample_rate)
    nyq = sample_rate / 2.0
    t = np.arange(n) / sample_rate
    f1, f2 = -nyq * 0.35, nyq * 0.42
    sig = (
        (np.exp(2j * np.pi * f1 * t) + np.exp(2j * np.pi * f2 * t)) / 2.0
    ).astype(np.complex64)
    return (sig + _awgn(n, snr_db, rng)).astype(np.complex64)


_GENERATORS = {
    "ambient": lambda dur, sr, snr, rng: generate_ambient(dur, sr, rng),
    "wifi": generate_wifi,
    "bluetooth": generate_bluetooth,
    "lora": generate_lora,
    "expresslrs": generate_expresslrs,
    "novel": generate_novel,
}


def generate(
    class_name: str,
    duration_s: float = config.DURATION_PER_CLASS_S,
    sample_rate: float = config.SAMPLE_RATE_HZ,
    snr_db: float = config.SNR_DB,
    seed: int | None = None,
) -> np.ndarray:
    """Dispatch to the named generator; returns complex IQ samples."""
    if class_name not in _GENERATORS:
        raise KeyError(f"unknown class {class_name!r}; have {sorted(_GENERATORS)}")
    rng = np.random.default_rng(seed)
    return _GENERATORS[class_name](duration_s, sample_rate, snr_db, rng)


def generate_all(
    duration_s: float = config.DURATION_PER_CLASS_S,
    sample_rate: float = config.SAMPLE_RATE_HZ,
    snr_db: float = config.SNR_DB,
    seed: int = config.RANDOM_SEED,
) -> dict[str, np.ndarray]:
    """Returns {class_name: iq} for every class in config.ALL_CLASSES."""
    # Distinct seeds per class so the synthetic captures are deterministic
    # and reproducible across runs.
    return {
        name: generate(name, duration_s, sample_rate, snr_db, seed=seed + i)
        for i, name in enumerate(config.ALL_CLASSES)
    }
