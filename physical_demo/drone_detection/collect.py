"""Case 3 - capture labeled feature rows into a dataset for train.py.

    python collect.py --label wifi   --sdr pluto --freq 2437000000 --stacks 200
    python collect.py --label quiet  --sdr pluto --freq 2437000000 --stacks 200
    python collect.py --label hopper --sdr pluto --freq 2437000000 --stacks 200

Each "stack" is `--stack-size` IQ windows reduced to one feature vector
(features.stack_features). Rows are appended to --out (npz: X, y). Drive the real
target / run the real ambient while collecting its label; validate on real signals.
"""
import argparse
import os

import numpy as np

import config
from features import stack_features


def append_dataset(path: str, rows, labels) -> None:
    """Append feature rows + labels to an npz dataset (create if missing). Testable."""
    rows = np.asarray(rows, dtype=float)
    labels = np.asarray(labels, dtype=object)
    if os.path.exists(path):
        d = np.load(path, allow_pickle=True)
        if len(d["X"]):
            rows = np.vstack([d["X"], rows])
            labels = np.concatenate([d["y"], labels])
    np.savez(path, X=rows, y=labels)


def _build_capture(args):
    if args.sdr == "pluto":
        from capture import PlutoCapture
        return PlutoCapture(center_freq_hz=int(args.freq), sample_rate=int(args.sample_rate), gain=args.gain)
    from capture import RtlCapture
    return RtlCapture(center_freq_hz=int(args.freq), sample_rate=int(args.sample_rate), gain=args.gain)


def main() -> None:
    parser = argparse.ArgumentParser(prog="collect", description="Capture labeled feature rows for the classifier.")
    parser.add_argument("--label", required=True, help="class label for these captures (e.g. wifi, quiet, hopper)")
    parser.add_argument("--sdr", choices=["rtl", "pluto"], default="pluto")
    parser.add_argument("--freq", type=float, default=2_437_000_000, metavar="HZ")
    parser.add_argument("--sample-rate", type=float, default=config.SAMPLE_RATE_HZ, metavar="HZ")
    parser.add_argument("--gain", default=config.GAIN)
    parser.add_argument("--stacks", type=int, default=200, help="number of feature rows to collect")
    parser.add_argument("--stack-size", type=int, default=8, help="IQ windows per feature row")
    parser.add_argument("--out", default="dataset.npz")
    args = parser.parse_args()

    fs = int(args.sample_rate)
    cap = _build_capture(args)
    print(f"collecting {args.stacks} rows for label='{args.label}' @ {args.freq/1e6:.3f} MHz ({args.sdr})")
    rows = []
    try:
        for k in range(args.stacks):
            windows = [cap.read_window(config.WINDOW_SAMPLES) for _ in range(args.stack_size)]
            if any(w.size == 0 for w in windows):
                print("[collect] stream ended"); break
            rows.append(stack_features(windows, fs))
            if (k + 1) % 20 == 0:
                print(f"  {k+1}/{args.stacks}")
    finally:
        cap.close()
    if rows:
        append_dataset(args.out, rows, [args.label] * len(rows))
        print(f"appended {len(rows)} rows -> {args.out}")


if __name__ == "__main__":
    main()
