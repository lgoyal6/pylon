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
PLUTO_MAX_TX_DBM = 5.0  # nominal Pluto output at gain=0 @ 2.4 GHz (approximate, uncalibrated)


RX_ANT_GAIN_DBI = 2.0  # assumed Pluto RX whip gain for the over-air received-power conversion


def dbm_to_atten(target_dbm: float, max_dbm: float = PLUTO_MAX_TX_DBM) -> float:
    """Approximate tx_hardwaregain (dB) for a target *output* dBm. Uncalibrated
    (±a few dB); clamped to the Pluto's range [-89.75, 0]."""
    return float(min(0.0, max(-89.75, target_dbm - max_dbm)))


def fspl_db(distance_m: float, freq_hz: float) -> float:
    """Free-space path loss (dB)."""
    return 20.0 * np.log10(distance_m) + 20.0 * np.log10(freq_hz) - 147.55


def rx_dbm_to_atten(rx_dbm: float, freq_hz: float, distance_m: float = 1.0,
                    grx_dbi: float = RX_ANT_GAIN_DBI, max_dbm: float = PLUTO_MAX_TX_DBM) -> float:
    """tx_hardwaregain for a target *received* power at `distance_m` over-air
    (free space): output = received + FSPL - Grx. Default 1 m. Uncalibrated."""
    output_dbm = rx_dbm + fspl_db(distance_m, freq_hz) - grx_dbi
    return dbm_to_atten(output_dbm, max_dbm)


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


def gfsk_hopper(n: int, sample_rate: float, n_channels: int = 5, sps: int = None,
               amplitude: float = 0.5, seed: int = 0) -> np.ndarray:
    """GFSK bursts hopping across a few narrowband channels — a *feature-faithful*
    'RC-link-like' emitter (GFSK, ~1 MHz, frequency-hopping), like a toy drone's
    nRF24/Beken link or Bluetooth. A controllable 'unknown' for the open-world
    demo + a training signal for the classifier. Not an exact protocol clone."""
    rng = np.random.default_rng(seed)
    if sps is None:
        sps = max(2, int(sample_rate / 1_000_000))  # ~1 Msym/s
    offsets = np.linspace(-0.3, 0.3, n_channels) * sample_rate
    # Gaussian pulse-shaping kernel (the 'G' in GFSK), numpy-only.
    k = np.arange(-2 * sps, 2 * sps + 1)
    gauss = np.exp(-0.5 * (k / (0.4 * sps)) ** 2)
    gauss /= gauss.sum()

    out = np.zeros(n, dtype=np.complex64)
    hop_len = max(sps * 4, n // 8)
    pos = 0
    while pos < n:
        seg_len = min(hop_len, n - pos)
        n_syms = seg_len // sps + 4
        nrz = np.repeat(rng.integers(0, 2, n_syms) * 2 - 1, sps).astype(float)
        shaped = np.convolve(nrz, gauss, mode="same")[:seg_len]
        phase = np.cumsum(shaped) * (np.pi * 0.5 / sps)  # FM, mod index ~0.5
        f_off = offsets[rng.integers(0, n_channels)]
        t = np.arange(seg_len) / sample_rate
        out[pos:pos + seg_len] = (amplitude * np.exp(1j * phase)
                                  * np.exp(2j * np.pi * f_off * t)).astype(np.complex64)
        pos += seg_len
    return out


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
    elif args.waveform == "hopper":
        wf = gfsk_hopper(n, args.sample_rate)  # RC/drone-like GFSK frequency-hopper
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
    parser.add_argument("--tx-dbm", type=float, default=None, metavar="DBM",
                        help="target RECEIVED power (dBm) at --distance over-air (default 1 m); adds free-space "
                             "path loss to set the output. Overrides --tx-atten. Approx/uncalibrated (±few dB).")
    parser.add_argument("--distance", type=float, default=1.0, metavar="M",
                        help="reference distance in meters for --tx-dbm (default 1.0)")
    parser.add_argument("--waveform", choices=["tone", "noise", "barrage", "sweep", "hopper"], default="tone",
                        help="tone/noise = clean emitters; barrage/sweep = jamming-like; hopper = RC/drone-like GFSK frequency-hopper")
    parser.add_argument("--offset", type=float, default=200_000, metavar="HZ",
                        help="tone offset from center (avoids the DC bin)")
    parser.add_argument("--bw", type=float, default=300_000, metavar="HZ",
                        help="noise bandwidth (--waveform noise)")
    parser.add_argument("--duty", type=float, default=1.0, metavar="FRAC",
                        help="on-fraction per buffer (<1 = sporadic/pulsed bursts; 1.0 = continuous)")
    parser.add_argument("--buffer", type=int, default=2 ** 15, metavar="SAMPLES",
                        help="TX buffer length (the cyclic chunk)")
    args = parser.parse_args()

    if args.tx_dbm is not None:
        tx_atten = rx_dbm_to_atten(args.tx_dbm, args.freq, distance_m=args.distance)
        power_note = (f"~{args.tx_dbm:.0f} dBm received @ {args.distance:.0f} m "
                      f"(atten {tx_atten:.1f} dB, ±few dB uncalibrated)")
    else:
        tx_atten = args.tx_atten
        power_note = f"tx_atten={tx_atten} dB"
    beacon = PlutoBeacon(int(args.freq), int(args.sample_rate), tx_atten_db=tx_atten)
    waveform = _build_waveform(args)
    print(f"Beacon ready: {args.waveform} @ {args.freq/1e6:.3f} MHz, {power_note}.  "
          f"(ISM self-test signal — not a jammer.)")
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
