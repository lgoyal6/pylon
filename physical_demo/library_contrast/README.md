# Library-Contrast Baseline — Iteration 3

The pitch metric for the project: **on a novel emitter that a Dedrone-style
signature library has never seen, our anomaly detector still catches it.**
This module is the experiment that produces the number.

## The setup

- **Library baseline** — `RandomForestClassifier` trained on a closed set of
  "known" emitter classes (`ambient`, `wifi`, `bluetooth`, `lora`,
  `expresslrs`). When its top-class confidence falls below
  `LIBRARY_NO_MATCH_THRESHOLD` it reports `no_match` (no detection).
- **Anomaly detector** — `IsolationForest` trained on `ambient` only. Anything
  unlike ambient scores high, whether or not it was ever seen.
- **Novel emitter** — `novel` is **held out from library training** entirely.
  It's a dual-tone CW pattern designed to be far from every known class.
- **Metric** — per-class miss rate (ambient column = false-positive rate). The
  headline cell is the `novel` column: library miss high, anomaly miss low.

## Run it

```bash
pip install -r requirements.txt
python evaluate.py
```

Output drops in `out/`:

- `miss_rates.png` — grouped bar chart, novel column highlighted.
- `results.md` — markdown table with per-class miss rates and the headline.

Useful flags:

```bash
python evaluate.py --duration-s 4 --snr-db 10 --seed 7 --output-dir runs/snr10
```

## How it relates to the rest of the project

This module is **decoupled from the RF detection service and the relay** — it
runs entirely on synthetic IQ (`synthetic.py`) so you can develop and ship the
pitch metric without needing the SDR to be wired up yet.

When real recordings exist, swap them in by replacing `synthetic.generate_all`
with a loader of your `.iq` files (one per class, same sample rate). Nothing
else changes — same features, same classifiers, same chart.

## Tests

```bash
python -m pytest
```

The suite covers feature extraction, both detectors' edge cases, and an
end-to-end run that asserts the headline behaviour:
`anomaly_miss_on_novel < library_miss_on_novel`. If that ever flips, the
synthetic generators or the threshold defaults regressed.

## What ships in the demo

> "We trained a signature-library baseline — like Dedrone — on four known
> emitters. We held out this fifth one as a novel adversary drone.
> **Library miss rate: X%. Our anomaly detector miss rate: Y%.** Same
> captures, both running side-by-side."

Drop the chart in the slide, cite the headline from the markdown table.
