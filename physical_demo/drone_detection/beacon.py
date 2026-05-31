"""Emitter CLI — transmit a benign low-power test signal from the ADALM-Pluto.

Purpose: a *controllable unknown emitter* for testing your OWN receiver (the RTL
running receiver.py at, e.g., 433.92 MHz ISM). You press Enter to toggle the
signal on/off; it should then appear on the receiver terminal. This is a
self-test beacon — low power, ISM band, into your own radio. It is NOT a jammer
and is not aimed at disrupting any device.

Run (Pluto on USB, libiio installed):

    python beacon.py --freq 433920000           # tone, default low power
    python beacon.py --freq 433920000 --waveform noise --bw 300000

The waveform generators are pure numpy (unit-tested without hardware); the TX
wrapper talks to the Pluto via pyadi-iio (lazy import).
"""
import argparse

import numpy as np

import config

TX_SCALE = 2 ** 14  # Pluto TX expects samples in int16 range; scale [-1,1] up to it.


def tone(n: int, sample_rate: float, offset_hz: float, amplitude: float = 0.5) -> np.ndarray:
    """A single complex tone at `offset_hz` from center — a clean narrowband
    'novel emitter' the anomaly detector flags as energy in one bin."""
    t = np.arange(n) / sample_rate
    return (amplitude * np.exp(2j * np.pi * offset_hz * t)).astype(np.complex64)


def band_limited_noise(n: int, sample_rate: float, bw_hz: float, seed: int = 0,
                       amplitude: float = 0.5) -> np.ndarray:
    """Noise confined to ±bw_hz/2 around center — a wideband emitter that the
    energy (occupied-bandwidth) detector also catches."""
    rng = np.random.default_rng(seed)
    x = rng.standard_normal(n) + 1j * rng.standard_normal(n)
    X = np.fft.fft(x)
    freqs = np.fft.fftfreq(n, 1 / sample_rate)
    X[np.abs(freqs) > bw_hz / 2] = 0  # zero out-of-band -> band-limited
    y = np.fft.ifft(X)
    y = y / np.max(np.abs(y)) * amplitude  # normalize to the requested amplitude
    return y.astype(np.complex64)


def chirp(n: int, sample_rate: float, bw_hz: float, amplitude: float = 0.5) -> np.ndarray:
    """A linear frequency sweep across ±bw_hz/2 — the classic *swept-jammer*
    signature: instantaneously narrow, but smears across the band over the window.
    Used as a detector test signal (the receiver should flag + classify it as
    jamming-like), not to disrupt anything."""
    t = np.arange(n) / sample_rate
    duration = n / sample_rate
    f0 = -bw_hz / 2.0
    sweep_rate = bw_hz / duration  # Hz per second
    phase = 2 * np.pi * (f0 * t + 0.5 * sweep_rate * t ** 2)
    return (amplitude * np.exp(1j * phase)).astype(np.complex64)


def apply_duty(waveform: np.ndarray, duty: float) -> np.ndarray:
    """Gate a waveform on for the first `duty` fraction of the buffer and off for
    the rest — gives a sporadic/pulsed character when looped (duty=1.0 = continuous)."""
    if duty >= 1.0:
        return waveform
    on = int(len(waveform) * max(duty, 0.0))
    gated = waveform.copy()
    gated[on:] = 0
    return gated


class PlutoBeacon:
    """Transmit a cyclic waveform from the Pluto. `sdr` is injectable for testing
    without hardware; live runs build adi.Pluto(uri) themselves (lazy import)."""

    def __init__(
        self,
        center_freq_hz: int,
        sample_rate: int,
        tx_atten_db: float = -30.0,  # tx_hardwaregain: 0 = max power, more negative = quieter
        uri: str = config.PLUTO_URI,
        sdr=None,
    ) -> None:
        if sdr is None:
            import adi  # lazy: only the live path needs libiio/pyadi-iio

            sdr = adi.Pluto(uri)
        self.sdr = sdr
        sdr.tx_lo = int(center_freq_hz)
        sdr.sample_rate = int(sample_rate)
        sdr.tx_rf_bandwidth = int(sample_rate)
        sdr.tx_hardwaregain_chan0 = float(tx_atten_db)

    def start(self, waveform: np.ndarray) -> None:
        """Begin transmitting `waveform` (assumed ~[-1, 1]) repeatedly until stop()."""
        self.sdr.tx_cyclic_buffer = True
        self.sdr.tx((waveform * TX_SCALE).astype(np.complex64))

    def stop(self) -> None:
        try:
            self.sdr.tx_destroy_buffer()
        except Exception:
            pass


def _build_waveform(args) -> np.ndarray:
    """tone/noise = clean test emitters; barrage/sweep = jamming-LIKE test signals
    (wide noise / frequency sweep) for validating jamming detection. --duty gates
    any of them into sporadic bursts. All are self-test signals, not jammers."""
    n = args.buffer
    if args.waveform == "noise":
        wf = band_limited_noise(n, args.sample_rate, args.bw)
    elif args.waveform == "barrage":
        wf = band_limited_noise(n, args.sample_rate, 0.4 * args.sample_rate)
    elif args.waveform == "sweep":
        # keep the swept span <50% of the band so the median-based occupancy
        # metric stays valid (a full-band sweep saturates the noise-floor estimate)
        wf = chirp(n, args.sample_rate, 0.4 * args.sample_rate)
    else:
        wf = tone(n, args.sample_rate, args.offset)
    return apply_duty(wf, args.duty)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="beacon",
        description="Pluto TX self-test beacon (toggle with Enter). Pairs with receiver.py.",
    )
    parser.add_argument("--freq", type=float, default=433_920_000, metavar="HZ",
                        help="center frequency (default 433.92 MHz ISM; must be in the RTL's <=1.75 GHz range)")
    parser.add_argument("--sample-rate", type=float, default=2_000_000, metavar="HZ")
    parser.add_argument("--tx-atten", type=float, default=-10.0, metavar="DB",
                        help="TX gain (0=max, more negative=quieter; default -10 = strong/clean). Go more negative if the RTL saturates.")
    parser.add_argument("--waveform", choices=["tone", "noise", "barrage", "sweep"], default="tone",
                        help="tone/noise = clean emitters; barrage/sweep = jamming-like test signals")
    parser.add_argument("--offset", type=float, default=200_000, metavar="HZ",
                        help="tone offset from center (avoids the DC bin)")
    parser.add_argument("--bw", type=float, default=300_000, metavar="HZ",
                        help="noise bandwidth (--waveform noise)")
    parser.add_argument("--duty", type=float, default=1.0, metavar="FRAC",
                        help="on-fraction per buffer (<1 = sporadic/pulsed bursts; 1.0 = continuous)")
    parser.add_argument("--buffer", type=int, default=2 ** 15, metavar="SAMPLES",
                        help="TX buffer length (the cyclic chunk)")
    args = parser.parse_args()

    beacon = PlutoBeacon(int(args.freq), int(args.sample_rate), tx_atten_db=args.tx_atten)
    waveform = _build_waveform(args)

    print(f"Beacon ready: {args.waveform} @ {args.freq/1e6:.3f} MHz, "
          f"tx_atten={args.tx_atten} dB.  (ISM self-test signal — not a jammer.)")
    print("Press Enter to TRANSMIT / stop.  Type q + Enter to quit.")
    transmitting = False
    try:
        while True:
            cmd = input()
            if cmd.strip().lower() in ("q", "quit", "exit"):
                break
            transmitting = not transmitting
            if transmitting:
                beacon.start(waveform)
                print("  ● TRANSMITTING — Enter to stop, q to quit")
            else:
                beacon.stop()
                print("  ○ idle — Enter to transmit, q to quit")
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        beacon.stop()
        print("\nbeacon stopped.")


if __name__ == "__main__":
    main()
