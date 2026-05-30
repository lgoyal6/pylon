"""Library-contrast experiment configuration.

The eval runs offline against synthetic or recorded IQ — these constants are
the knobs you'd tune to match the real RF capture once it exists.
"""
from __future__ import annotations

# --- Signal / capture geometry ----------------------------------------------
# RTL-SDR (NESDR SMArt v5) practical sample rate; max is 2.4 MHz but 2.048 MHz
# is the stable sweet spot.
SAMPLE_RATE_HZ: float = 2_048_000.0
# 915 MHz ISM by default — what an ExpressLRS / SiK telemetry link would use.
CENTER_FREQ_HZ: float = 915_000_000.0

# --- Windowing / features ---------------------------------------------------
# 1024-sample windows ≈ 500 µs at 2.048 MS/s — short enough to resolve BT-style
# hops, long enough to keep FFT resolution reasonable.
WINDOW_SAMPLES: int = 1024
HOP_SAMPLES: int = 512
# Downsample the raw FFT to N bins to keep the feature vector small for RF.
N_PSD_BINS: int = 64

# --- Dataset shape ----------------------------------------------------------
DURATION_PER_CLASS_S: float = 2.0  # 2 s × 2.048 MS/s ≈ 4k samples per class
SNR_DB: float = 15.0
TRAIN_FRACTION: float = 0.6  # remainder goes to held-out test
RANDOM_SEED: int = 1337

# --- Class names ------------------------------------------------------------
# These are the "known" emitter classes the library is trained on; `novel` is
# held out from training to simulate an adversary the library has never seen.
AMBIENT_CLASS: str = "ambient"
KNOWN_EMITTER_CLASSES: tuple[str, ...] = ("wifi", "bluetooth", "lora", "expresslrs")
NOVEL_CLASS: str = "novel"
ALL_CLASSES: tuple[str, ...] = (AMBIENT_CLASS, *KNOWN_EMITTER_CLASSES, NOVEL_CLASS)

# --- Detector thresholds ----------------------------------------------------
# Library "matches" anything within this quantile of intra-training distances.
# 0.95 = accept inputs whose nearest training neighbour is at most as far as
# the 95th percentile of training-set self-distances. Stricter values reject
# more, which catches more novel emitters but risks losing known ones.
LIBRARY_MATCH_DISTANCE_QUANTILE: float = 0.95
# Anomaly score quantile (over the ambient training set) used as the
# "this is unusual" cutoff. 0.95 = flag the top 5% noisiest ambient windows.
ANOMALY_THRESHOLD_QUANTILE: float = 0.95

# --- Artifact outputs -------------------------------------------------------
DEFAULT_OUTPUT_DIR: str = "out"
CHART_FILENAME: str = "miss_rates.png"
TABLE_FILENAME: str = "results.md"
