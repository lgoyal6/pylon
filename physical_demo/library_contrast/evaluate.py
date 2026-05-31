"""End-to-end evaluation harness.

Generates (or loads) per-class IQ → extracts features → trains the library
baseline on known classes + ambient → trains the anomaly detector on ambient
only → runs both on a held-out test set → reports miss rates per class.

The pitch metric: miss rate on the `novel` class. Library: high. Anomaly: low.
"""
from __future__ import annotations

import argparse
import os
from dataclasses import dataclass

import matplotlib

matplotlib.use("Agg")  # headless — write the PNG without needing a display.
import matplotlib.pyplot as plt
import numpy as np

import config
import synthetic
from anomaly_detector import AnomalyDetector
from features import iq_to_features
from library_baseline import LibraryBaseline


@dataclass
class ClassResult:
    name: str
    library_miss_rate: float  # for ambient this is "false-positive rate" instead
    anomaly_miss_rate: float
    n_windows: int


@dataclass
class EvalResult:
    per_class: list[ClassResult]
    library_overall_novel_miss: float
    anomaly_overall_novel_miss: float


def _build_dataset(
    duration_s: float, snr_db: float, seed: int
) -> dict[str, np.ndarray]:
    """Per-class feature matrices: {class_name: (n_windows, feat_dim)}."""
    captures = synthetic.generate_all(
        duration_s=duration_s, sample_rate=config.SAMPLE_RATE_HZ, snr_db=snr_db, seed=seed
    )
    return {name: iq_to_features(iq) for name, iq in captures.items()}


def _train_test_split(
    features_by_class: dict[str, np.ndarray], train_fraction: float, rng: np.random.Generator
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    """Per-class random split — keeps test windows from every class for eval."""
    train, test = {}, {}
    for name, X in features_by_class.items():
        idx = rng.permutation(X.shape[0])
        cut = int(train_fraction * X.shape[0])
        train[name] = X[idx[:cut]]
        test[name] = X[idx[cut:]]
    return train, test


def _miss_rate_on(detector_is_detection, X: np.ndarray, expect_detection: bool) -> float:
    """Miss rate: fraction of windows where the detector got the binary call wrong.

    - For emitter classes (expect_detection=True): miss = detector returned False.
    - For ambient (expect_detection=False): miss = detector returned True
      (i.e. false-positive rate, reported in the same column for symmetry).
    """
    if X.shape[0] == 0:
        return 0.0
    flags = detector_is_detection(X)
    if expect_detection:
        return float((~flags).mean())
    return float(flags.mean())


def evaluate(
    duration_s: float = config.DURATION_PER_CLASS_S,
    snr_db: float = config.SNR_DB,
    seed: int = config.RANDOM_SEED,
    train_fraction: float = config.TRAIN_FRACTION,
) -> EvalResult:
    rng = np.random.default_rng(seed)
    features_by_class = _build_dataset(duration_s, snr_db, seed)
    train, test = _train_test_split(features_by_class, train_fraction, rng)

    # Library trains on ambient + known emitters. Novel is held out entirely.
    library_train_classes = (config.AMBIENT_CLASS, *config.KNOWN_EMITTER_CLASSES)
    X_lib_train = np.concatenate([train[c] for c in library_train_classes])
    y_lib_train = np.concatenate(
        [np.full(train[c].shape[0], c, dtype=object) for c in library_train_classes]
    )
    library = LibraryBaseline().fit(X_lib_train, y_lib_train)

    # Anomaly detector sees only ambient — that's the whole point of the wedge.
    anomaly = AnomalyDetector().fit(train[config.AMBIENT_CLASS])

    per_class: list[ClassResult] = []
    for name in config.ALL_CLASSES:
        X = test[name]
        expect = name != config.AMBIENT_CLASS
        per_class.append(
            ClassResult(
                name=name,
                library_miss_rate=_miss_rate_on(library.is_detection, X, expect),
                anomaly_miss_rate=_miss_rate_on(anomaly.is_detection, X, expect),
                n_windows=int(X.shape[0]),
            )
        )

    novel_row = next(r for r in per_class if r.name == config.NOVEL_CLASS)
    return EvalResult(
        per_class=per_class,
        library_overall_novel_miss=novel_row.library_miss_rate,
        anomaly_overall_novel_miss=novel_row.anomaly_miss_rate,
    )


def write_chart(result: EvalResult, path: str) -> None:
    names = [r.name for r in result.per_class]
    lib = [r.library_miss_rate for r in result.per_class]
    ano = [r.anomaly_miss_rate for r in result.per_class]
    x = np.arange(len(names))
    width = 0.38

    fig, ax = plt.subplots(figsize=(9, 5))
    bars_lib = ax.bar(x - width / 2, lib, width, label="Library baseline", color="#c0504d")
    bars_ano = ax.bar(x + width / 2, ano, width, label="Anomaly detector (ours)", color="#4f81bd")

    # Highlight the novel column — the pitch metric lives here.
    novel_idx = names.index(config.NOVEL_CLASS)
    ax.axvspan(novel_idx - 0.5, novel_idx + 0.5, color="#fff3bf", alpha=0.6, zorder=0)
    ax.annotate(
        "held-out novel\n(never in library training)",
        xy=(novel_idx, max(lib[novel_idx], ano[novel_idx]) + 0.05),
        ha="center",
        fontsize=9,
        color="#8a6d00",
    )

    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=20)
    ax.set_ylabel("Miss rate (ambient column = false-positive rate)")
    ax.set_ylim(0, 1.05)
    ax.set_title("Library vs anomaly detector — per-class miss rate")
    ax.legend()
    ax.grid(axis="y", linestyle=":", alpha=0.4)

    for bars in (bars_lib, bars_ano):
        for b in bars:
            ax.annotate(
                f"{b.get_height():.0%}",
                xy=(b.get_x() + b.get_width() / 2, b.get_height()),
                xytext=(0, 3),
                textcoords="offset points",
                ha="center",
                fontsize=8,
            )

    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def write_table(result: EvalResult, path: str) -> None:
    lines = [
        "# Library vs anomaly detector — miss rates",
        "",
        "| Class | Role | Library miss | Anomaly miss | Test windows |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for r in result.per_class:
        if r.name == config.AMBIENT_CLASS:
            role = "ambient (FP rate)"
        elif r.name == config.NOVEL_CLASS:
            role = "**held-out novel**"
        else:
            role = "known emitter"
        lines.append(
            f"| {r.name} | {role} | {r.library_miss_rate:.0%} | "
            f"{r.anomaly_miss_rate:.0%} | {r.n_windows} |"
        )
    lines += [
        "",
        f"**Pitch metric (novel emitter):** library miss "
        f"`{result.library_overall_novel_miss:.0%}` vs anomaly "
        f"`{result.anomaly_overall_novel_miss:.0%}`.",
        "",
    ]
    with open(path, "w") as f:
        f.write("\n".join(lines))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="library_contrast",
        description="Iteration 3 — library vs anomaly miss-rate experiment.",
    )
    parser.add_argument("--output-dir", default=config.DEFAULT_OUTPUT_DIR)
    parser.add_argument("--duration-s", type=float, default=config.DURATION_PER_CLASS_S)
    parser.add_argument("--snr-db", type=float, default=config.SNR_DB)
    parser.add_argument("--seed", type=int, default=config.RANDOM_SEED)
    args = parser.parse_args(argv)

    os.makedirs(args.output_dir, exist_ok=True)
    result = evaluate(duration_s=args.duration_s, snr_db=args.snr_db, seed=args.seed)

    chart_path = os.path.join(args.output_dir, config.CHART_FILENAME)
    table_path = os.path.join(args.output_dir, config.TABLE_FILENAME)
    write_chart(result, chart_path)
    write_table(result, table_path)

    print(f"chart: {chart_path}")
    print(f"table: {table_path}")
    print()
    print(f"{'class':<12} {'library miss':>14} {'anomaly miss':>14}")
    print("-" * 44)
    for r in result.per_class:
        print(f"{r.name:<12} {r.library_miss_rate:>14.0%} {r.anomaly_miss_rate:>14.0%}")
    print()
    print(
        f"==> NOVEL: library miss {result.library_overall_novel_miss:.0%}, "
        f"anomaly miss {result.anomaly_overall_novel_miss:.0%}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
