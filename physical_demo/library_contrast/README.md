# Library-Contrast Baseline - Iteration 3

The pitch metric for the project: **on a novel emitter that a Dedrone-style
signature library has never seen, our anomaly detector still catches it.**
This module is the experiment that produces the number.

## The setup

- **Library baseline** - nearest-neighbor signature matching trained on a closed set of
  "known" emitter classes (`ambient`, `wifi`, `bluetooth`, `lora`,
  `expresslrs`). Beyond the training-distance quantile it reports `no_match`
  (no detection). This is an illustrative baseline, not a vendor implementation.
- **Anomaly detector** - `IsolationForest` trained on `ambient` only. Anything
  unlike ambient scores high, whether or not it was ever seen.
- **Novel emitter** - `novel` is **held out from library training** entirely.
  It's a dual-tone CW pattern designed to be far from every known class.
- **Metric** - per-class miss rate (ambient column = false-positive rate). The
  headline cell is the `novel` column: library miss high, anomaly miss low.

## Run it

```bash
pip install -r requirements.txt
python evaluate.py
```

Output drops in `out/`:

- `miss_rates.png` - grouped bar chart, novel column highlighted.
- `results.md` - markdown table with per-class miss rates and the headline.

Useful flags:

```bash
python evaluate.py --duration-s 4 --snr-db 10 --seed 7 --output-dir runs/snr10
```

## How it relates to the rest of the project

This module is **decoupled from the RF detection service and the relay** - it
runs entirely on synthetic IQ (`synthetic.py`) so you can develop and ship the
pitch metric without needing the SDR to be wired up yet.

The random window split in `evaluate.py` is a synthetic demonstration. Overlapping
windows from one recording are correlated and do not establish field generalization.
Use the separate recording-level replay below for grouped studies.

## Recording-level replay

`recordings.py` loads bounded `.npy`, `cf32_le`, `ci16_le` or `cu8` IQ, verifies
SHA-256 and sample counts, and rejects corrupt samples and capture loss. A version-1
JSON manifest supplies recording/session/site/device/day and emitter identities,
source and license, explicit `synthetic`, `chamber` or `field` provenance, fixed gain,
clock offset and RF geometry. Unknown gain or clock metadata is a protocol blocker,
not an assumed zero. Each capture declares `train`, `calibration` or `test`, its
`target` boolean, and whether its emitter identity is `novel` at test time.

Replay limits each input file to 64 MiB and each materialized window matrix to
128 MiB. The study also caps total samples and feature windows. The matrix limit
handles dense overlap, which can expand a small IQ file far beyond its file size.

Split recordings before deriving windows. Recording IDs, sessions and content hashes
must be disjoint across all three partitions. Declared `holdout_axes` additionally
enforce site, receiver or day separation. A receiver split alone can leak the same
transmission session. Background and interference remain explicit negative classes.

Freeze a protocol containing the exact manifest SHA-256, `source_sha256` from
`heldout_study.source_hashes()`, seed, window/hop geometry and
`false_alerted_windows_per_hour` budget. Then run from this directory:

```bash
python heldout_study.py /absolute/path/manifest.json /absolute/path/protocol.json /absolute/path/result.json
```

The runner refuses changed inputs/source or an existing output. It retains native
signature/anomaly decisions, calibration-budget versions of both and a median-power
normalized anomaly arm. Thresholds use negative calibration recordings only. The
normalization is a software gain intervention, not physical receiver calibration.
All arms see the same captures. Results preserve raw calibration scores, test flags,
per-class slices, session bootstrap uncertainty, first-flag delay from recording start,
and missed recordings. `summarize(result['raw'], seed)` reconstructs the summaries.
Bootstrap intervals are `null` when the relevant target or negative set has fewer
than two independent acquisition sessions. Results include both session counts and
`bootstrap_min_sessions`; a single session cannot establish sampling uncertainty.
Flagged windows use hop-time exposure; they are not independent alerts or operator
notifications. Calibration budgets can fail on a shifted test environment. Short
replays cannot establish operational false alerts/hour or broad drone reliability.

Keep input IQ, frozen protocols and results outside the repository. Recovery is a new
experiment ID and output path, preserving old results. No model is deployed by this
runner. Rollback is selecting the unchanged `evaluate.py` demonstration or prior
versioned study inputs. Physical startup, tuning and receive-only permissions remain
separate device/operator checks.

## Tests

```bash
python -m pytest
```

The suite covers feature extraction, both detectors' edge cases, and an
end-to-end run that asserts the headline behaviour:
`anomaly_miss_on_novel < library_miss_on_novel`. If that ever flips, the
synthetic generators or the threshold defaults regressed.

## What ships in the demo

> "We trained a signature-library baseline - like Dedrone - on four known
> emitters. We held out this fifth one as a novel adversary drone.
> **Library miss rate: X%. Our anomaly detector miss rate: Y%.** Same
> captures, both running side-by-side."

Drop the chart in the slide, cite the headline from the markdown table.
