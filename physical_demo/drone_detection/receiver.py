"""Receiver CLI — RTL-SDR live detection display.

Captures from the NESDR/RTL, runs the open-world anomaly detector (or the energy
detector), and prints detections live to the terminal. Pairs with beacon.py: tune
both to the same frequency (default 433.92 MHz ISM), let this learn the ambient,
then toggle the beacon and watch the line flip to DETECTED.

Run (RTL on USB):

    python receiver.py --freq 433920000                 # anomaly detector (product)
    python receiver.py --freq 433920000 --detector energy

Reuses RtlCapture + AnomalyDetector/EnergyThresholdDetector — no new detection
logic, just a live display instead of the FastAPI service.
"""
import argparse
import sys
import time

import config
from anomaly import AnomalyDetector
from capture import RtlCapture
from detector import EnergyThresholdDetector, classify_emitter


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="receiver",
        description="RTL-SDR live detection display. Pairs with beacon.py.",
    )
    parser.add_argument("--freq", type=float, default=433_920_000, metavar="HZ")
    parser.add_argument("--sample-rate", type=float, default=config.SAMPLE_RATE_HZ, metavar="HZ")
    parser.add_argument("--gain", default=config.GAIN, help="tuner gain in dB, or 'auto'")
    parser.add_argument("--detector", choices=["anomaly", "energy"], default="anomaly")
    parser.add_argument("--learn-seconds", type=float, default=8.0, metavar="SECONDS",
                        help="anomaly: ambient-learning duration (keep the beacon OFF)")
    args = parser.parse_args()

    fs = int(args.sample_rate)
    window = config.WINDOW_SAMPLES
    cap = RtlCapture(center_freq_hz=int(args.freq), sample_rate=fs, gain=args.gain)
    if args.detector == "energy":
        detector = EnergyThresholdDetector(sample_rate=fs)
    else:
        learn_windows = max(1, int(args.learn_seconds * fs / window))
        detector = AnomalyDetector(sample_rate=fs, learn_windows=learn_windows)

    print(f"Receiver: {args.detector} detector @ {args.freq/1e6:.3f} MHz, gain={args.gain}")
    if args.detector == "anomaly":
        print(f"Learning ambient ~{args.learn_seconds:.0f}s — keep the beacon OFF. Then start beacon.py.")

    on = off = 0
    detected = False
    try:
        while True:
            iq = cap.read_window(window)
            if iq.size == 0:
                print("\n[stream ended — no RTL device?]")
                break
            res = detector.evaluate(iq)

            if getattr(detector, "fitted", True) is False:  # anomaly learn phase
                pct = 100 * len(detector._buffer) / detector.learn_windows
                sys.stdout.write(f"\r  learning ambient… {pct:5.1f}%   ")
                sys.stdout.flush()
                continue

            if res["detected"]:
                on, off = on + 1, 0
            else:
                off, on = off + 1, 0
            kind = classify_emitter(res["occupied_bw_hz"], res["flatness"], fs)
            if not detected and on >= config.DEBOUNCE_ON:
                detected = True
                print(f"\n  🚨 {time.strftime('%H:%M:%S')}  SIGNAL DETECTED [{kind}]  "
                      f"score={res['anomaly_score']:.2f} snr={res['snr_db']:.1f}dB "
                      f"bw={res['occupied_bw_hz']/1e3:.0f}kHz flat={res['flatness']:.2f}")
            elif detected and off >= config.DEBOUNCE_OFF:
                detected = False
                print(f"\n  ○ {time.strftime('%H:%M:%S')}  cleared — quiet again")

            tag = f"🚨 SIGNAL: {kind}" if detected else "· quiet"
            sys.stdout.write(f"\r  [{tag}] score={res['anomaly_score']:.2f} "
                             f"snr={res['snr_db']:.1f}dB bw={res['occupied_bw_hz']/1e3:.0f}kHz "
                             f"flat={res['flatness']:.2f}   ")
            sys.stdout.flush()
    except KeyboardInterrupt:
        pass
    finally:
        cap.close()
        print("\nreceiver stopped.")


if __name__ == "__main__":
    main()
